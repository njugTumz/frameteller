import asyncio

import pytest

from frameteller.application.errors import ModelUnavailableError
from frameteller.application.ports import Job
from frameteller.infrastructure.jobs import InProcessJobQueue, JobStatus


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, JobStatus, str | None]] = []
        self.ran: list[str] = []
        self.fail_once: set[str] = set()

    async def handler(self, job: Job) -> None:
        await asyncio.sleep(0)
        if job.idempotency_key in self.fail_once:
            self.fail_once.discard(job.idempotency_key)
            raise ModelUnavailableError("muse-image-1.0", "HTTP 503")
        self.ran.append(job.idempotency_key)

    async def on_status(self, job: Job, status: JobStatus, message: str | None) -> None:
        self.events.append((job.idempotency_key, status, message))


def queue(r: Recorder, concurrency: int = 2) -> InProcessJobQueue:
    return InProcessJobQueue({"panel": r.handler}, concurrency=concurrency, on_status=r.on_status)


async def test_runs_jobs_and_reports_status() -> None:
    r = Recorder()
    q = queue(r)
    assert await q.enqueue(Job("panel", "k1"))
    await q.join()
    assert r.ran == ["k1"]
    assert [s for _, s, _ in r.events] == [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED]
    assert q.status("k1") is JobStatus.SUCCEEDED


async def test_same_idempotency_key_runs_once() -> None:
    r = Recorder()
    q = queue(r)
    assert await q.enqueue(Job("panel", "k1"))
    assert not await q.enqueue(Job("panel", "k1"))
    await q.join()
    assert not await q.enqueue(Job("panel", "k1"))
    assert r.ran == ["k1"]


async def test_failed_job_reports_user_message_and_can_be_retried() -> None:
    r = Recorder()
    r.fail_once = {"k1"}
    q = queue(r)
    await q.enqueue(Job("panel", "k1"))
    await q.join()
    _, status, message = r.events[-1]
    assert status is JobStatus.FAILED
    assert message is not None
    assert "trouble" in message
    assert await q.enqueue(Job("panel", "k1"))
    await q.join()
    assert r.ran == ["k1"]


async def test_concurrency_is_bounded() -> None:
    running = peak = 0

    async def handler(job: Job) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1

    q = InProcessJobQueue({"panel": handler}, concurrency=2)
    for i in range(6):
        await q.enqueue(Job("panel", f"k{i}"))
    await q.join()
    assert peak == 2


async def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="no handler"):
        await InProcessJobQueue({}).enqueue(Job("panel", "k1"))


async def test_unexpected_errors_get_a_generic_message_and_a_broken_callback_is_contained() -> None:
    async def boom(job: Job) -> None:
        raise KeyError("bug")

    statuses: list[tuple[JobStatus, str | None]] = []

    async def on_status(job: Job, status: JobStatus, message: str | None) -> None:
        statuses.append((status, message))
        if status is JobStatus.RUNNING:
            raise RuntimeError("websocket gone")

    q = InProcessJobQueue({"panel": boom}, on_status=on_status)
    await q.enqueue(Job("panel", "k1"))
    await q.join()
    assert statuses[-1] == (JobStatus.FAILED, "Something went wrong.")


async def test_join_returns_when_jobs_queue_more_jobs() -> None:
    """Regression: a render queues a review that queues an edit. Gathering tasks that were already done never
    yielded, so their done-callbacks never ran and join spun forever."""
    ran: list[str] = []
    queue: InProcessJobQueue

    async def first(job: Job) -> None:
        ran.append(job.kind)
        await queue.enqueue(Job("second", "second:1", {}))

    async def second(job: Job) -> None:
        ran.append(job.kind)
        await queue.enqueue(Job("third", "third:1", {}))

    async def third(job: Job) -> None:
        ran.append(job.kind)

    queue = InProcessJobQueue({"first": first, "second": second, "third": third})
    await queue.enqueue(Job("first", "first:1", {}))
    await asyncio.wait_for(queue.join(), 2)
    assert ran == ["first", "second", "third"]


async def test_exports_run_in_their_own_lane_and_waiters_learn_their_place() -> None:
    from frameteller.application.capacity import Gate

    release = asyncio.Event()
    ran: list[str] = []
    places: list[tuple[str, int]] = []

    async def export(job: Job) -> None:
        ran.append(job.idempotency_key)
        await release.wait()

    async def panel(job: Job) -> None:
        ran.append(job.idempotency_key)

    async def on_waiting(job: Job, place: int, estimate_s: float) -> None:
        places.append((job.idempotency_key, place))

    q = InProcessJobQueue(
        {"export": export, "panel": panel},
        concurrency=4,
        lanes={"export": Gate("exports", 1, typical_s=30)},
        on_waiting=on_waiting,
    )
    for key in ("e1", "e2"):
        await q.enqueue(Job("export", key))
    await q.enqueue(Job("panel", "p1"))
    await asyncio.sleep(0.01)
    assert ran == ["e1", "p1"]  # the panel did not wait behind the exports
    assert places == [("e2", 1)]
    release.set()
    await q.join()
    assert ran == ["e1", "p1", "e2"]
    assert places[-1] == ("e2", 0)
