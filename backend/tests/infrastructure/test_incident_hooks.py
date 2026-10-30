"""The Errors tab's hooks: every model attempt counts toward health; a call or job that gives up is an error."""

import asyncio
import contextlib
from datetime import UTC, datetime

from frameteller.application.budget import BudgetCalendar
from frameteller.application.errors import ModelUnavailableError
from frameteller.application.incidents import IncidentDesk, component_var, plain_message
from frameteller.application.ports import Job
from frameteller.infrastructure.jobs import InProcessJobQueue
from frameteller.infrastructure.observability import log_context
from frameteller.infrastructure.resilience import Breakers, ModelCaller, RetryPolicy
from tests.fakes import FixedClock, InMemoryMediaStorage, InMemorySpendLedger
from tests.infrastructure.test_resilience import Harness, status_error


def desk() -> IncidentDesk:
    clock = FixedClock(datetime(2026, 11, 5, 10, 0, tzinfo=UTC))
    return IncidentDesk(InMemoryMediaStorage(), clock, BudgetCalendar(10, utc_offset_hours=4).day)


async def no_sleep(_: float) -> None:
    return None


async def test_retries_count_toward_health_and_a_call_that_gives_up_is_an_error() -> None:
    d = desk()
    h = Harness()
    caller = ModelCaller(h.ledger, h.breakers, sleep=no_sleep, rand=lambda: 1.0, incidents=d)
    policy = RetryPolicy(attempts=2, timeout_s=5)
    assert await caller.call("muse-image-1.0", "generate", h.flaky(status_error(503)), policy) == "ok"
    with log_context(project_id="p7"), contextlib.suppress(ModelUnavailableError):
        await caller.call("muse-image-1.0", "generate", h.flaky(*[status_error(503)] * 2), policy)
    [health] = await d.health()
    assert (health.calls, health.failures, health.retries) == (4, 3, 2)
    [error] = await d.recent()
    assert (error.component, error.code, error.project_id) == ("image", "model_unavailable", "p7")
    assert error.message == plain_message(ModelUnavailableError("muse-image-1.0", "HTTP 503"))  # our own words
    assert "HTTP 503" not in error.message  # never the provider's detail


async def test_a_review_inside_a_gallery_job_is_the_gallerys() -> None:
    d = desk()
    caller = ModelCaller(InMemorySpendLedger(), Breakers(3, 30), sleep=no_sleep, incidents=d)
    token = component_var.set("gallery")
    try:
        await caller.call("muse-spark-1.3", "review", Harness().flaky(status_error(400)), RetryPolicy(attempts=1))
    except Exception:
        pass
    finally:
        component_var.reset(token)
    assert (await d.recent())[0].component == "gallery"


async def test_a_job_that_gives_up_reaches_the_failure_callback_with_its_component_set() -> None:
    seen: list[tuple[str, str, str | None]] = []

    async def fails(job: Job) -> None:
        await asyncio.sleep(0)
        seen.append(("ran", job.kind, component_var.get()))
        raise RuntimeError("nope")

    async def on_failure(job: Job, exc: Exception) -> None:
        seen.append(("failed", job.kind, type(exc).__name__))

    queue = InProcessJobQueue({"export_animatic": fails}, on_failure=on_failure)
    await queue.enqueue(Job(kind="export_animatic", idempotency_key="k1", payload={}))
    await queue.join()
    assert seen == [("ran", "export_animatic", "export"), ("failed", "export_animatic", "RuntimeError")]
    assert component_var.get() is None  # only inside the job's own task
