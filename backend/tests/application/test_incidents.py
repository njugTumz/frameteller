"""The admin's Errors tab: what is recorded (and what never is), counts, model health, failed jobs and reports."""

from datetime import UTC, datetime, timedelta

import pytest

from frameteller.application.budget import BudgetCalendar
from frameteller.application.errors import BudgetExceededError, LimitReachedError, ProjectNotFoundError
from frameteller.application.events import SessionFailed
from frameteller.application.incidents import (
    MAX_MESSAGE,
    IncidentDesk,
    RecordingEvents,
    ReportProblem,
    RetryFailedJob,
    RetryRefusedError,
    clean,
    component_var,
    error_code,
    job_component,
    model_component,
    plain_message,
    visitor_var,
)
from frameteller.application.ports import Job
from tests.builders import project
from tests.fakes import (
    FixedClock,
    InMemoryJobQueue,
    InMemoryMediaStorage,
    InMemoryProjectRepository,
    InMemoryVisitorQuota,
    RecordingPublisher,
    SequentialIds,
)

T0 = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
DAY = BudgetCalendar(10, utc_offset_hours=4).day


def desk(storage: InMemoryMediaStorage | None = None, clock: FixedClock | None = None) -> IncidentDesk:
    return IncidentDesk(storage or InMemoryMediaStorage(), clock or FixedClock(T0), DAY)


def test_components_come_from_the_job_then_the_model() -> None:
    assert job_component("export_animatic") == "export"
    assert job_component("gallery_submission") == "gallery"
    assert job_component("unknown") == "api"
    assert model_component("muse-voice-transcribe-1.0") == "voice"
    assert model_component("muse-spark-1.3") == "director"
    assert model_component("muse-spark-1.3", "review") == "supervisor"
    assert model_component("azure-tts") == "tts"
    assert model_component("sam-3.1") == "sam"
    token = component_var.set("gallery")
    try:
        assert model_component("muse-spark-1.3", "review") == "gallery"  # the gallery's moderation review
        assert model_component("muse-image-1.0") == "gallery"
    finally:
        component_var.reset(token)


def test_messages_are_one_short_line_with_no_keys_tokens_or_ip_addresses() -> None:
    text = clean("failed with LLM_abcdefghijkl and Bearer abc.def from 10.1.2.3\n  again " + "x" * 300)
    assert "LLM_" not in text
    assert "abc.def" not in text
    assert "10.1.2.3" not in text
    assert "\n" not in text
    assert len(text) == MAX_MESSAGE
    assert clean("a" * 100, 80).endswith("…")
    assert plain_message(BudgetExceededError("p1", 1.0)) == BudgetExceededError("p1", 1.0).user_message
    assert plain_message(KeyError("secret transcript")) == "Unexpected KeyError."  # never the exception's text
    assert error_code(BudgetExceededError("p1", 1.0)) == "budget_exceeded"


async def test_recent_errors_newest_first_with_the_visitor_hash_and_counts_for_24_hours() -> None:
    clock = FixedClock(T0)
    d = desk(clock=clock)
    token = visitor_var.set("a1b2c3d4e5f6")
    try:
        await d.error("image", "model_timeout", "Muse Image took too long.", project_id="p1")
    finally:
        visitor_var.reset(token)
    clock.current = T0 + timedelta(hours=3)
    await d.error("nonsense", "invalid_request", "POST /projects: body.style: bad")
    clock.current = T0 + timedelta(hours=26)  # the next day: the first error is over 24 hours old
    await d.error("export", "model_timeout", "Export took too long.")

    recent = await d.recent()
    assert [(i.component, i.code) for i in recent] == [
        ("export", "model_timeout"),
        ("api", "invalid_request"),  # an unknown component is "api"
        ("image", "model_timeout"),
    ]
    assert (recent[-1].project_id, recent[-1].visitor) == ("p1", "a1b2c3d4e5f6")
    assert await d.counts() == {"invalid_request": 1, "model_timeout": 1}


async def test_only_the_last_100_and_they_survive_a_restart() -> None:
    storage = InMemoryMediaStorage()
    d = desk(storage)
    for n in range(105):
        await d.error("api", "error", f"error {n}")
    again = desk(storage)  # a new revision reads what the old one wrote
    recent = await again.recent()
    assert len(recent) == 100
    assert recent[0].message == "error 104"


async def test_model_health_today_with_failures_retries_and_p95() -> None:
    storage = InMemoryMediaStorage()
    d = desk(storage)
    for latency in range(1, 101):
        await d.model_call("muse-image-1.0", latency * 10, ok=True, retry=False)
    await d.model_call("muse-image-1.0", 30_000, ok=False, retry=False)
    await d.model_call("muse-image-1.0", 2_000, ok=True, retry=True)
    [health] = await d.health()
    assert (health.model, health.calls, health.failures, health.retries) == ("muse-image-1.0", 102, 1, 1)
    assert health.p95_ms == 960  # latencies of successful calls only
    await d.flush()
    [again] = await desk(storage).health()
    assert again.calls == 102


async def test_a_failed_job_can_be_retried_once_and_comes_back_if_it_fails_again() -> None:
    d = desk()
    queue = InMemoryJobQueue()
    job = Job(kind="generate_panel", idempotency_key="generate_panel:p1:s1:1", payload={"project_id": "p1"})
    await d.job_failed(job, RuntimeError("the transcript says hello"))
    [failed] = await d.failed_jobs()
    assert (failed.component, failed.code, failed.message) == ("image", "runtime", "Unexpected RuntimeError.")
    assert (await d.recent())[0].code == "job_failed.runtime"

    is_open = True

    async def budget_open() -> bool:
        return is_open

    retry = RetryFailedJob(d, queue, budget_open)
    await retry.execute(job.idempotency_key)
    assert queue.jobs == [job]
    assert await d.failed_jobs() == []
    await d.job_failed(job, BudgetExceededError("p1", 1.0))  # the retry gave up too
    [again] = await d.failed_jobs()
    assert (again.retries, again.code) == (1, "budget_exceeded")

    with pytest.raises(RetryRefusedError, match="no longer in the list"):
        await retry.execute("nothing:like:this")
    is_open = False
    with pytest.raises(RetryRefusedError, match="budget is spent"):
        await retry.execute(job.idempotency_key)
    assert len(await d.failed_jobs()) == 1  # refused: still there


async def test_a_retry_that_cannot_start_stays_in_the_list() -> None:
    d = desk()
    queue = InMemoryJobQueue()
    job = Job(kind="export_animatic", idempotency_key="export:p1:1", payload={"project_id": "p1"})
    await queue.enqueue(job)  # already running
    await d.job_failed(job, RuntimeError())

    async def budget_open() -> bool:
        return True

    with pytest.raises(RetryRefusedError, match="already running"):
        await RetryFailedJob(d, queue, budget_open).execute(job.idempotency_key)
    assert [j.key for j in await d.failed_jobs()] == [job.idempotency_key]


async def test_failed_jobs_older_than_30_days_are_forgotten() -> None:
    clock = FixedClock(T0)
    d = desk(clock=clock)
    await d.job_failed(Job(kind="export_animatic", idempotency_key="k", payload={}), RuntimeError())
    clock.current = T0 + timedelta(days=31)
    assert await d.failed_jobs() == []


async def test_problem_reports_are_limited_per_visitor_and_need_a_real_project() -> None:
    repo = InMemoryProjectRepository(project())
    d = desk()
    report = ReportProblem(d, repo, InMemoryVisitorQuota(), SequentialIds("r"), FixedClock(T0), DAY)
    first = await report.execute("p1", "  The export\nnever finished. " + "x" * 600, "visitor-1")
    assert len(first.text) == 500
    for _ in range(4):
        await report.execute("p1", "", "visitor-1")
    with pytest.raises(LimitReachedError, match="5 reports today"):
        await report.execute("p1", "again", "visitor-1")
    await report.execute("p1", "someone else", "visitor-2")
    with pytest.raises(ProjectNotFoundError):
        await report.execute("nope", "x", "visitor-3")
    reports = await d.reports()
    assert reports[0].text == "someone else"
    assert len(reports) == 6


async def test_session_failures_with_a_source_are_errors_and_every_event_still_goes_out() -> None:
    d = desk()
    hub = RecordingPublisher()
    events = RecordingEvents(hub, d)
    await events.publish("p1", SessionFailed("The transcriber stopped.", fatal=True, source="voice"))
    await events.publish("p1", SessionFailed("Real people can't be characters."))  # a refusal, not an error
    assert len(hub.events) == 2
    [incident] = await d.recent()
    assert (incident.component, incident.code, incident.project_id) == ("voice", "session_ended", "p1")


async def test_a_broken_store_never_breaks_the_caller() -> None:
    class Broken(InMemoryMediaStorage):
        async def put(self, key: str, data: bytes, content_type: str):  # type: ignore[no-untyped-def]
            raise OSError("disk full")

    d = desk(Broken())
    await d.error("api", "error", "still fine")
    await d.model_call("muse-spark-1.3", 10, ok=True, retry=False)
    await d.flush()
