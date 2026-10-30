"""InProcessJobQueue: asyncio tasks with idempotency keys and status callbacks.

Most jobs share one pool of slots (they mostly wait on models, whose own gates limit the calls in flight). A job
kind can have its own gate instead, a lane: exports run in theirs, so a line of exports never holds up drawing
(ADR 0016). While a job waits at any gate, its place in line goes to `on_waiting`.

Fine for one container. Jobs are lost on restart, which is acceptable because every job is idempotent and
the client can re-request it; a durable queue can replace this behind JobQueuePort.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum

from frameteller.application.capacity import Gate, waiting_var
from frameteller.application.errors import ApplicationError
from frameteller.application.incidents import component_var, job_component
from frameteller.application.ports import Job

log = logging.getLogger("frameteller.jobs")

Handler = Callable[[Job], Awaitable[None]]


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


StatusCallback = Callable[[Job, JobStatus, str | None], Awaitable[None]]
# (job, place in line, estimated seconds); place 0: the wait is over.
WaitingCallback = Callable[[Job, int, float], Awaitable[None]]
# A job that gave up, with why: the admin's Errors tab lists it with a Retry button.
FailureCallback = Callable[[Job, Exception], Awaitable[None]]


class InProcessJobQueue:
    def __init__(
        self,
        handlers: dict[str, Handler],
        *,
        concurrency: int = 3,
        on_status: StatusCallback | None = None,
        lanes: Mapping[str, Gate] | None = None,
        on_waiting: WaitingCallback | None = None,
        on_failure: FailureCallback | None = None,
    ) -> None:
        self._handlers = handlers
        self._slots = Gate("jobs", concurrency, typical_s=20)
        self._lanes = dict(lanes or {})
        self._on_status, self._on_waiting, self._on_failure = on_status, on_waiting, on_failure
        self._status: dict[str, JobStatus] = {}
        self._messages: dict[str, str] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def enqueue(self, job: Job) -> bool:
        if job.kind not in self._handlers:
            raise ValueError(f"no handler for job kind {job.kind!r}")
        if self._status.get(job.idempotency_key) not in (None, JobStatus.FAILED):
            return False  # queued, running or done: never run twice
        await self._set(job, JobStatus.QUEUED)
        task = asyncio.create_task(self._run(job), name=job.idempotency_key)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    def status(self, idempotency_key: str) -> JobStatus | None:
        return self._status.get(idempotency_key)

    def message(self, idempotency_key: str) -> str | None:
        """The user-facing message of a failed job."""
        return self._messages.get(idempotency_key)

    async def join(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks))
            # Finished tasks leave the set in done-callbacks, which run only once the loop gets a turn: without
            # this, gathering tasks that are already done never yields and the loop spins forever.
            await asyncio.sleep(0)

    def gates(self) -> list[Gate]:
        return [self._slots, *self._lanes.values()]

    async def _run(self, job: Job) -> None:
        component_var.set(job_component(job.kind))  # this task's own context: its model calls are labelled
        if self._on_waiting is not None:
            on_waiting = self._on_waiting

            async def report(place: int, estimate_s: float) -> None:
                await on_waiting(job, place, estimate_s)

            waiting_var.set(report)  # this task's own context: model gates inside the job report through it
        async with self._lanes.get(job.kind, self._slots).slot():
            await self._set(job, JobStatus.RUNNING)
            try:
                await self._handlers[job.kind](job)
            except Exception as exc:
                message = exc.user_message if isinstance(exc, ApplicationError) else "Something went wrong."
                log.exception("job failed", extra={"job_kind": job.kind, "job_key": job.idempotency_key})
                await self._set(job, JobStatus.FAILED, message)
                if self._on_failure is not None:
                    try:
                        await self._on_failure(job, exc)
                    except Exception:
                        log.exception("job failure callback failed", extra={"job_key": job.idempotency_key})
                return
            await self._set(job, JobStatus.SUCCEEDED)

    async def _set(self, job: Job, status: JobStatus, message: str | None = None) -> None:
        self._status[job.idempotency_key] = status
        if message is not None:
            self._messages[job.idempotency_key] = message
        if self._on_status:
            try:
                await self._on_status(job, status, message)
            except Exception:
                log.exception("job status callback failed", extra={"job_key": job.idempotency_key})
