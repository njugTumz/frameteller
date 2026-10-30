"""The admin's Errors tab: recent errors, problem reports, failed jobs and model health, kept in our own storage.

One document per budget day (`admin/incidents/<day>.json`) holds that day's errors, problem reports and model
health; failed jobs that gave up are in `admin/failed-jobs.json` so the admin can retry them. Nothing here is
served by /media (it serves `projects/` only), and everything is deleted after 30 days: the storage lifecycle rule
removes day documents 30 days after their last change, and the desk prunes older days and jobs itself.

What is kept is deliberately small: a component, an error code, our own plain-language message (at most 160
characters, user text at most 80), the project id and the first 12 characters of the visitor hash. Never keys,
tokens, audio, transcripts or IP addresses.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from frameteller.application import jobs as kinds
from frameteller.application.errors import ApplicationError, LimitReachedError
from frameteller.application.events import ProjectEvent, SessionFailed
from frameteller.application.ports import (
    Clock,
    EventPublisher,
    IdGenerator,
    Job,
    JobQueuePort,
    MediaStoragePort,
    ProjectRepository,
    VisitorQuota,
)
from frameteller.domain import MediaRef

log = logging.getLogger("frameteller.incidents")

component_var: ContextVar[str | None] = ContextVar("component", default=None)
visitor_var: ContextVar[str | None] = ContextVar("visitor", default=None)  # a hash prefix, never the IP

COMPONENTS = ("voice", "director", "image", "sam", "export", "tts", "supervisor", "gallery", "api")
RECENT = 100
KEEP_DAYS = 30
PER_DAY = 1000  # errors kept per day, so a storm can't grow a document without bound
LATENCIES = 2000  # latencies kept per model per day, for p95
MAX_MESSAGE = 160
MAX_USER_TEXT = 80
MAX_REPORT = 500
FAILED_JOBS = "admin/failed-jobs.json"
FLUSH_EVERY_S = 15.0  # model health is written at most this often; errors and reports at once

_JOB_COMPONENTS = {
    kinds.GENERATE_PANEL: "image",
    kinds.EDIT_PANEL: "image",
    kinds.GENERATE_CAST: "image",
    kinds.COMPOSE_PANEL: "image",
    kinds.PRE_SEGMENT_PANEL: "sam",
    kinds.EXPORT_ANIMATIC: "export",
    kinds.SUPERVISE_PANEL: "supervisor",
    kinds.REVIEW_SHEET: "supervisor",
    kinds.GALLERY_SUBMISSION: "gallery",
}
_SECRET = re.compile(r"(?i)\bLLM_[A-Za-z0-9_\-]{8,}|\bbearer\s+\S+|\b(?:\d{1,3}\.){3}\d{1,3}\b")


def job_component(kind: str) -> str:
    return _JOB_COMPONENTS.get(kind, "api")


def model_component(model: str, operation: str = "") -> str:
    """Which part of the studio a model call served: the job's, else the model's own."""
    current = component_var.get()
    if operation == "review" and current != "gallery":
        return "supervisor"
    if current:
        return current
    name = model.lower()
    for marker, component in (
        ("voice-transcribe", "voice"),
        ("image", "image"),
        ("sam", "sam"),
        ("tts", "tts"),
        ("glimmer", "supervisor"),
    ):
        if marker in name:
            return component
    return "director"  # Spark and Wonder


def error_code(exc: BaseException) -> str:
    """ModelTimeoutError -> model_timeout."""
    name = type(exc).__name__.removesuffix("Error") or "Error"
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def clean(text: str, limit: int = MAX_MESSAGE) -> str:
    """One line, no keys, tokens or IP addresses, at most `limit` characters."""
    one = " ".join(_SECRET.sub("[redacted]", text).split())
    return one if len(one) <= limit else one[: limit - 1] + "…"


def plain_message(exc: BaseException) -> str:
    """Our own words for an error: an application error's user message, else only what kind of error it was."""
    if isinstance(exc, ApplicationError):
        return clean(exc.user_message)
    return f"Unexpected {type(exc).__name__}."


@dataclass(frozen=True, slots=True)
class Incident:
    at: str
    component: str
    code: str
    message: str
    project_id: str | None = None
    visitor: str | None = None


@dataclass(frozen=True, slots=True)
class ProblemReport:
    id: str
    at: str
    project_id: str
    text: str
    visitor: str | None = None


@dataclass(slots=True)
class FailedJob:
    key: str
    kind: str
    payload: dict[str, Any]
    component: str
    code: str
    message: str
    at: str
    project_id: str | None = None
    retries: int = 0


@dataclass(frozen=True, slots=True)
class ModelHealth:
    model: str
    calls: int
    failures: int
    retries: int
    p95_ms: int | None


@dataclass(slots=True)
class _Day:
    errors: list[dict[str, Any]] = field(default_factory=list)
    reports: list[dict[str, Any]] = field(default_factory=list)
    health: dict[str, dict[str, Any]] = field(default_factory=dict)


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


class IncidentDesk:
    """Records and reads back what went wrong. One replica (ADR 0009): a lock and an in-memory day suffice.

    Recording never raises: a broken desk must not break the request or job it describes.
    """

    def __init__(self, storage: MediaStoragePort, clock: Clock, day: Callable[[datetime], str]) -> None:
        self._storage, self._clock, self._day = storage, clock, day
        self._lock = asyncio.Lock()
        self._days: dict[str, _Day] = {}
        self._jobs: dict[str, FailedJob] | None = None
        self._retries: dict[str, int] = {}  # retries so far of jobs taken out for a retry
        self._dirty: set[str] = set()
        self._flushed = 0.0

    # ---- recording ----

    async def error(self, component: str, code: str, message: str, *, project_id: str | None = None) -> None:
        incident = Incident(
            at=self._clock.now().isoformat(),
            component=component if component in COMPONENTS else "api",
            code=clean(code, 40),
            message=clean(message),
            project_id=project_id,
            visitor=visitor_var.get(),
        )
        await self._safely(self._add_error, incident)

    async def report(self, project_id: str, text: str, report_id: str) -> ProblemReport:
        report = ProblemReport(
            report_id, self._clock.now().isoformat(), project_id, clean(text, MAX_REPORT), visitor_var.get()
        )
        await self._safely(self._add_report, report)
        return report

    async def job_failed(self, job: Job, exc: BaseException) -> None:
        failed = FailedJob(
            key=job.idempotency_key,
            kind=job.kind,
            payload=dict(job.payload),
            component=job_component(job.kind),
            code=error_code(exc),
            message=plain_message(exc),
            at=self._clock.now().isoformat(),
            project_id=str(job.payload.get("project_id") or "") or None,
        )
        await self.error(failed.component, f"job_failed.{failed.code}", failed.message, project_id=failed.project_id)
        await self._safely(self._add_job, failed)

    async def model_call(self, model: str, latency_ms: int, *, ok: bool, retry: bool) -> None:
        await self._safely(self._add_call, model, latency_ms, ok, retry)

    async def flush(self) -> None:
        """Write any model health not yet saved (on shutdown)."""
        await self._safely(self._save, True)

    # ---- reading ----

    async def recent(self, limit: int = RECENT) -> list[Incident]:
        found: list[Incident] = []
        for day in self._recent_days():
            doc = await self._load(day)
            found += [Incident(**e) for e in reversed(doc.errors)]
            if len(found) >= limit:
                break
        return found[:limit]

    async def counts(self, hours: int = 24) -> dict[str, int]:
        """Errors by code over the last `hours`, most first."""
        since = (self._clock.now() - timedelta(hours=hours)).isoformat()
        counts: dict[str, int] = {}
        for day in self._recent_days()[:2]:
            for e in (await self._load(day)).errors:
                if e["at"] >= since:
                    counts[e["code"]] = counts.get(e["code"], 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    async def health(self) -> list[ModelHealth]:
        """Today's model calls: how many, how many failed, how many were retries, and p95 latency."""
        doc = await self._load(self._today())
        return [
            ModelHealth(model, h["calls"], h["failures"], h["retries"], _p95(h["latencies"]))
            for model, h in sorted(doc.health.items())
        ]

    async def reports(self, limit: int = RECENT) -> list[ProblemReport]:
        found: list[ProblemReport] = []
        for day in self._recent_days():
            found += [ProblemReport(**r) for r in reversed((await self._load(day)).reports)]
            if len(found) >= limit:
                break
        return found[:limit]

    async def failed_jobs(self) -> list[FailedJob]:
        jobs = await self._load_jobs()
        return sorted(jobs.values(), key=lambda j: j.at, reverse=True)

    async def take_job(self, key: str) -> FailedJob | None:
        """Remove a failed job for a retry; if the retry fails too, it comes back with its own failure."""
        async with self._lock:
            jobs = await self._load_jobs()
            job = jobs.pop(key, None)
            if job is not None:
                self._retries[key] = job.retries + 1
                await self._save_jobs(jobs)
            return job

    async def put_back(self, job: FailedJob) -> None:
        """The retry could not start: the job stays in the list as it was."""
        async with self._lock:
            self._retries.pop(job.key, None)
            jobs = await self._load_jobs()
            jobs[job.key] = job
            await self._save_jobs(jobs)

    # ---- storage ----

    def _today(self) -> str:
        return self._day(self._clock.now())

    def _recent_days(self) -> list[str]:
        now = self._clock.now()
        return list(dict.fromkeys(self._day(now - timedelta(days=n)) for n in range(KEEP_DAYS)))

    @staticmethod
    def _key(day: str) -> str:
        return f"admin/incidents/{day}.json"

    async def _load(self, day: str) -> _Day:
        if day not in self._days:
            ref = MediaRef(self._key(day))
            doc = json.loads(await self._storage.get(ref)) if await self._storage.exists(ref) else {}
            self._days[day] = _Day(doc.get("errors", []), doc.get("reports", []), doc.get("health", {}))
            if len(self._days) > KEEP_DAYS + 2:  # keep only recent days in memory
                for old in sorted(self._days)[: len(self._days) - KEEP_DAYS - 2]:
                    self._days.pop(old, None)
        return self._days[day]

    async def _save(self, force: bool) -> None:
        if not self._dirty or (not force and time.monotonic() - self._flushed < FLUSH_EVERY_S):
            return
        for day in sorted(self._dirty):
            doc = self._days.get(day)
            if doc is not None:
                body = {"errors": doc.errors, "reports": doc.reports, "health": doc.health}
                await self._storage.put(self._key(day), json.dumps(body).encode(), "application/json")
        self._dirty.clear()
        self._flushed = time.monotonic()

    async def _add_error(self, incident: Incident) -> None:
        day = self._today()
        doc = await self._load(day)
        doc.errors = [*doc.errors, asdict(incident)][-PER_DAY:]
        self._dirty.add(day)
        await self._save(True)

    async def _add_report(self, report: ProblemReport) -> None:
        day = self._today()
        doc = await self._load(day)
        doc.reports = [*doc.reports, asdict(report)][-PER_DAY:]
        self._dirty.add(day)
        await self._save(True)

    async def _add_call(self, model: str, latency_ms: int, ok: bool, retry: bool) -> None:
        day = self._today()
        doc = await self._load(day)
        h = doc.health.setdefault(model, {"calls": 0, "failures": 0, "retries": 0, "latencies": []})
        h["calls"] += 1
        h["failures"] += 0 if ok else 1
        h["retries"] += 1 if retry else 0
        if ok:
            h["latencies"] = [*h["latencies"], latency_ms][-LATENCIES:]
        self._dirty.add(day)
        await self._save(False)

    async def _load_jobs(self) -> dict[str, FailedJob]:
        if self._jobs is None:
            ref = MediaRef(FAILED_JOBS)
            raw = json.loads(await self._storage.get(ref)) if await self._storage.exists(ref) else {}
            self._jobs = {k: FailedJob(**v) for k, v in raw.items()}
        cutoff = (self._clock.now() - timedelta(days=KEEP_DAYS)).isoformat()
        self._jobs = {k: j for k, j in self._jobs.items() if j.at >= cutoff}
        return self._jobs

    async def _save_jobs(self, jobs: dict[str, FailedJob]) -> None:
        body = json.dumps({k: asdict(j) for k, j in jobs.items()}).encode()
        await self._storage.put(FAILED_JOBS, body, "application/json")

    async def _add_job(self, failed: FailedJob) -> None:
        jobs = await self._load_jobs()
        failed.retries = self._retries.pop(failed.key, 0)
        jobs[failed.key] = failed
        await self._save_jobs(jobs)

    async def _safely(self, action: Callable[..., Any], *args: Any) -> None:
        try:
            async with self._lock:
                await action(*args)
        except Exception:
            log.warning("could not record an incident", exc_info=True)


class RetryFailedJob:
    """The admin retries a job that gave up. Refused while the studio is paused or today's budget is spent; the
    job itself then goes through the same budget, limits and queues as any other."""

    def __init__(self, desk: IncidentDesk, jobs: JobQueuePort, budget_open: Callable[[], Awaitable[bool]]) -> None:
        self._desk, self._jobs, self._budget_open = desk, jobs, budget_open

    async def execute(self, key: str) -> FailedJob:
        if not await self._budget_open():
            raise RetryRefusedError("Today's budget is spent or the studio is paused. Try again tomorrow.")
        failed = await self._desk.take_job(key)
        if failed is None:
            raise RetryRefusedError("That job is no longer in the list.")
        try:
            started = await self._jobs.enqueue(
                Job(kind=failed.kind, idempotency_key=failed.key, payload=failed.payload)
            )
        except Exception:
            await self._desk.put_back(failed)
            raise
        if not started:
            await self._desk.put_back(failed)
            raise RetryRefusedError("That job is already running or has finished.")
        return failed


class RetryRefusedError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.user_message = message


class RecordingEvents:
    """The live session's events, passed on unchanged; a session failure with a source is also an error."""

    def __init__(self, events: EventPublisher, desk: IncidentDesk) -> None:
        self._events, self._desk = events, desk

    async def publish(self, project_id: str, event: ProjectEvent) -> None:
        if isinstance(event, SessionFailed) and event.source:
            code = "session_ended" if event.fatal else "session_failed"
            await self._desk.error(event.source, code, event.message, project_id=project_id)
        await self._events.publish(project_id, event)


REPORTS_PER_DAY = 5


class ReportProblem:
    """ "Report a problem" in the studio: the visitor's words (optional, at most 500 characters) with the project id.

    A few per visitor a day, so the button can't fill the admin's tab; the per-minute rate limit applies too.
    """

    def __init__(
        self,
        desk: IncidentDesk,
        repo: ProjectRepository,
        quota: VisitorQuota | None,
        ids: IdGenerator,
        clock: Clock,
        day: Callable[[datetime], str],
        per_day: int = REPORTS_PER_DAY,
    ) -> None:
        self._desk, self._repo, self._quota, self._ids = desk, repo, quota, ids
        self._clock, self._day, self._per_day = clock, day, per_day

    async def execute(self, project_id: str, text: str, visitor: str) -> ProblemReport:
        await self._repo.get(project_id)  # a report belongs to a real project
        day = self._day(self._clock.now())
        if self._quota is not None and await self._quota.used(visitor, day, "problem_reports") >= self._per_day:
            raise LimitReachedError(
                f"You've sent {self._per_day} reports today. Thank you: we're looking at them. More open at midnight."
            )
        report = await self._desk.report(project_id, text, self._ids.new_id())
        if self._quota is not None:
            await self._quota.add(visitor, day, "problem_reports")
        return report
