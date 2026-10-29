"""Public-demo allowances: per visitor, per project and per live session, and the studio status."""

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest

from frameteller.application.audio import BYTES_PER_MS
from frameteller.application.budget import LimitBudgetGuard
from frameteller.application.errors import BudgetExceededError, LimitReachedError, StudioFullError
from frameteller.application.events import SessionEnded, SessionFailed, ShotCreated
from frameteller.application.limits import EXPORTS, RENDERS, DemoLimits, ProjectAllowance, VisitorAllowance
from frameteller.application.ports import DirectedTurn, ShotDraft, SpeechOptions
from frameteller.application.use_cases import (
    AnimaticOptions,
    CorrectTranscript,
    CreateProject,
    DirectTurn,
    GeneratePanel,
    GetStudioStatus,
    RequestAnimaticExport,
    RequestCastReferences,
    RequestPanelEdit,
    RequestPanelRender,
    RunVoiceSession,
)
from frameteller.domain import Framing, TranscriptTurn
from tests.application.conftest import World
from tests.builders import project
from tests.fakes import (
    FakeDirector,
    FakeSpeechToText,
    FixedClock,
    InMemoryJobQueue,
    InMemoryMediaStorage,
    InMemoryProjectRepository,
    InMemorySpendLedger,
    InMemoryVisitorQuota,
    RecordingPublisher,
    SequentialIds,
)

SMALL = DemoLimits(
    projects_per_visitor_per_day=2, narration_ms_per_session=1000, shots_per_episode=4, renders_per_project=2,
    exports_per_project=2,
)  # fmt: skip


def draft(action: str) -> ShotDraft:
    return ShotDraft(Framing.MEDIUM, ("mira",), "a narrow alley", action, "", ("?",), 1000)


# ---- per visitor ----


async def test_a_visitor_starts_only_so_many_stories_a_day() -> None:
    clock, quota = FixedClock(), InMemoryVisitorQuota()
    create = CreateProject(InMemoryProjectRepository(), SequentialIds("p"), VisitorAllowance(quota, clock, SMALL))

    await create.execute("One", visitor="v1")
    await create.execute("Two", visitor="v1")
    with pytest.raises(LimitReachedError) as refused:
        await create.execute("Three", visitor="v1")

    assert "started 2 stories today" in refused.value.user_message
    await create.execute("Someone else's", visitor="v2")  # counted per visitor
    clock.current += timedelta(days=1)
    await create.execute("Tomorrow", visitor="v1")  # a new day, a new allowance
    assert quota.counts[("v1", "2026-10-28", "projects")] == 2


async def test_without_a_visitor_or_an_allowance_projects_are_not_counted() -> None:
    quota = InMemoryVisitorQuota()
    allowance = VisitorAllowance(quota, FixedClock(), SMALL)
    limited = CreateProject(InMemoryProjectRepository(), SequentialIds("p"), allowance)
    for _ in range(3):
        await limited.execute("A test, not a visitor")
        await CreateProject(InMemoryProjectRepository(), SequentialIds("q")).execute("Local", visitor="v1")
    assert not quota.counts


# ---- per project ----


async def test_renders_and_edits_share_one_allowance_and_repeats_are_free(world: World) -> None:
    allowance = ProjectAllowance(world.repo, SMALL)
    render = RequestPanelRender(world.repo, world.jobs, allowance)

    await render.execute("p1", "s1", "low")
    await render.execute("p1", "s1", "low")  # the same revision again: deduplicated, not counted
    await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", "s1", 1)
    await RequestPanelEdit(world.repo, world.jobs, allowance).execute("p1", "s1", "her coat is red now")
    assert world.project().usage == {RENDERS: 2}
    queued = len(world.jobs.jobs)

    with pytest.raises(LimitReachedError, match="used its 2 drawings and edits"):
        await render.execute("p1", "s2", "low")
    with pytest.raises(LimitReachedError):
        await RequestPanelEdit(world.repo, world.jobs, allowance).execute("p1", "s1", "a bigger moon")
    assert len(world.jobs.jobs) == queued  # nothing was queued past the limit


async def test_exports_per_project_are_limited(world: World) -> None:
    for shot_id in ("s1", "s2", "s3"):
        await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", shot_id, 1)
    export = RequestAnimaticExport(world.repo, world.jobs, ProjectAllowance(world.repo, SMALL))

    await export.execute("p1")
    await export.execute("p1")  # the same export again, still under the limit: free
    await export.execute("p1", AnimaticOptions(subtitles=False))
    with pytest.raises(LimitReachedError, match="exported 2 times"):
        await export.execute(
            "p1", AnimaticOptions(subtitles=False)
        )  # at the limit even a repeat is refused: download it instead
    assert world.project().usage == {EXPORTS: 2}


async def test_the_shot_limit_keeps_the_first_shots_and_says_so() -> None:
    repo = InMemoryProjectRepository(project(shots=3))
    three = DirectedTurn((), (draft("one"), draft("two"), draft("three")))
    director = FakeDirector({"4": three, "5": three})
    directed = await DirectTurn(repo, director, SequentialIds("shot"), max_shots_per_episode=4).execute(
        "p1", TranscriptTurn("4", "Three more beats", 0, 3000)
    )

    assert [s.action for s in directed.shots] == ["one"]
    assert directed.capped
    assert len(repo.peek("p1").shots) == 4

    again = await DirectTurn(repo, director, SequentialIds("more"), max_shots_per_episode=4).execute(
        "p1", TranscriptTurn("5", "And three more", 3000, 6000)
    )
    assert (again.shots, again.capped) == ((), True)
    assert repo.peek("p1").turns[-1].text == "And three more"  # the words are still kept in the transcript


# ---- per live session ----


def voice_session(
    repo: InMemoryProjectRepository, speech: FakeSpeechToText, director: FakeDirector, limits: DemoLimits
) -> tuple[RunVoiceSession, RecordingPublisher]:
    events, jobs = RecordingPublisher(), InMemoryJobQueue()
    cast = RequestCastReferences(repo, jobs, SequentialIds("n"))
    run = RunVoiceSession(
        speech,
        DirectTurn(repo, director, SequentialIds("shot"), max_shots_per_episode=limits.shots_per_episode),
        CorrectTranscript(repo, director, SequentialIds("fix"), cast, events),
        cast,
        events,
        SequentialIds("s"),
        repo,
        InMemoryMediaStorage(),
        limits,
    )
    return run, events


async def audio(ms: int, chunk_ms: int = 100) -> AsyncIterator[bytes]:
    for _ in range(ms // chunk_ms):
        yield b"\x00\x00" * (chunk_ms * BYTES_PER_MS // 2)


def failures(events: RecordingPublisher) -> list[str]:
    return [e.message for _, e in events.events if isinstance(e, SessionFailed)]


async def test_a_telling_stops_at_the_narration_limit() -> None:
    speech = FakeSpeechToText()
    run, events = voice_session(InMemoryProjectRepository(project()), speech, FakeDirector(), SMALL)

    await run.execute("p1", audio(5000), SpeechOptions())

    assert len(speech.audio) == 1000 * BYTES_PER_MS  # nothing past one second reached the transcriber
    assert failures(events) == [SMALL.narration_full]
    assert any(isinstance(e, SessionEnded) for _, e in events.events)


async def test_a_full_storyboard_is_said_once_per_session() -> None:
    turns = [TranscriptTurn(str(n), f"Beat {n}", n * 1000, n * 1000 + 900) for n in range(3)]
    director = FakeDirector({str(n): DirectedTurn((), (draft(f"beat {n}"),)) for n in range(3)})
    repo = InMemoryProjectRepository(project(shots=3))
    run, events = voice_session(repo, FakeSpeechToText(turns), director, SMALL)

    await run.execute("p1", audio(500), SpeechOptions())

    assert sum(isinstance(e, ShotCreated) for _, e in events.events) == 1
    assert failures(events) == [SMALL.shots_full]
    assert len(repo.peek("p1").shots) == 4


async def test_the_director_refusal_reaches_the_narrator() -> None:
    no = "Frameteller draws original characters only. Who is your hero instead?"
    director = FakeDirector({"0": DirectedTurn((), (), refusal=no)})
    turn = TranscriptTurn("0", "A famous wizard walks in", 0, 2000)
    run, events = voice_session(InMemoryProjectRepository(project()), FakeSpeechToText([turn]), director, SMALL)

    await run.execute("p1", audio(500), SpeechOptions())

    assert failures(events) == [no]
    assert not any(isinstance(e, ShotCreated) for _, e in events.events)


# ---- the whole studio ----


async def test_the_global_daily_cap_says_the_studio_is_full() -> None:
    ledger = InMemorySpendLedger()
    guard = LimitBudgetGuard(ledger, FixedClock(), per_project_usd=1.0, per_day_usd=0.02)
    await guard.charge("p1", 0.01, "panel")
    await guard.charge("p2", 0.01, "panel")

    with pytest.raises(StudioFullError) as full:
        await guard.charge("p3", 0.01, "panel")
    assert isinstance(full.value, BudgetExceededError)
    assert full.value.user_message == "The studio is full for today. Come back tomorrow."


async def test_studio_status_is_full_once_the_day_cap_is_reached() -> None:
    ledger, clock = InMemorySpendLedger(), FixedClock()
    status = GetStudioStatus(ledger, clock, per_day_usd=0.05, paused=False, limits=SMALL)
    assert not (await status.execute()).full

    ledger.by_day["2026-10-28"] = 0.045  # within a cent: no model call fits any more
    now = await status.execute()
    assert (now.full, now.paused, now.limits) == (True, False, SMALL)

    clock.current += timedelta(days=1)
    assert not (await status.execute()).full
    assert (await GetStudioStatus(ledger, clock, per_day_usd=1, paused=True, limits=SMALL).execute()).paused
