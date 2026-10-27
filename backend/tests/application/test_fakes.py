"""The fakes stand in for real adapters, so they get a few checks of their own."""

from frameteller.application.ports import Job
from tests.builders import turn
from tests.fakes import FakeSpeechToText, InMemoryJobQueue, RecordingBudget


async def test_job_queue_dedupes_by_idempotency_key() -> None:
    q = InMemoryJobQueue()
    assert await q.enqueue(Job("k", "key-1"))
    assert not await q.enqueue(Job("k", "key-1"))
    assert len(q.jobs) == 1


async def test_speech_to_text_fake_returns_turns() -> None:
    assert await FakeSpeechToText([turn(1)]).transcribe(b"pcm", ["Mira"]) == [turn(1)]


async def test_recording_budget_totals() -> None:
    b = RecordingBudget()
    await b.charge("p", 0.01, "a")
    await b.charge("p", 0.0025, "b")
    assert round(b.total, 4) == 0.0125
