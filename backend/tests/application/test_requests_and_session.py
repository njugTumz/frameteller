import asyncio
from collections.abc import AsyncIterator

import pytest

from frameteller.application.errors import ModelTimeoutError, ProjectNotFoundError
from frameteller.application.events import (
    CastProposed,
    SessionEnded,
    SessionFailed,
    ShotCreated,
    TranscriptUpdated,
    TurnFinished,
)
from frameteller.application.jobs import EDIT_PANEL, GENERATE_CAST, GENERATE_PANEL
from frameteller.application.ports import (
    DirectedTurn,
    PartialTranscript,
    ShotDraft,
    SpeechOptions,
    TurnCompleted,
    TurnStarted,
)
from frameteller.application.use_cases import (
    ApproveCast,
    CorrectTranscript,
    CreateProject,
    DirectTurn,
    EditPanelAppearance,
    EditPanelByCommand,
    FindShot,
    GenerateCastReferences,
    GenerateCharacterReference,
    GeneratePanel,
    GetProject,
    RequestCastReferences,
    RequestPanelEdit,
    RequestPanelRender,
    RunVoiceSession,
)
from frameteller.domain import (
    CastNotApprovedError,
    Character,
    Framing,
    InvalidValueError,
    MediaRef,
    PanelNotReadyError,
    TranscriptTurn,
    UnknownCharacterError,
    UnknownShotError,
)
from tests.application.conftest import World
from tests.builders import project, turn
from tests.fakes import (
    FakeDirector,
    FakeSpeechToText,
    InMemoryJobQueue,
    InMemoryMediaStorage,
    InMemoryProjectRepository,
    RecordingPublisher,
    SequentialIds,
)

OWL = Character("owl", "Owl", "a small brown owl with round spectacles")


def draft(*characters: str, turn_id: str) -> ShotDraft:
    return ShotDraft(Framing.WIDE, tuple(characters), "rooftop", "the owl lands", "", (turn_id,), 4000)


# ---- projects ----


async def test_create_get_and_find_shot() -> None:
    repo = InMemoryProjectRepository(project(shots=2))
    created = await CreateProject(repo, SequentialIds("p")).execute("  The Lantern Cat ")
    assert (created.id, created.title) == ("p1", "The Lantern Cat")
    assert (await GetProject(repo).execute("p1")).id == "p1"
    with pytest.raises(ProjectNotFoundError):
        await GetProject(repo).execute("nope")

    repo = InMemoryProjectRepository(project(shots=3))
    assert (await FindShot(repo).execute("p1", 2)).id == "s2"
    with pytest.raises(UnknownShotError):
        await FindShot(repo).execute("p1", 9)


# ---- concurrency: model calls happen outside the atomic update ----


async def test_concurrent_turn_and_render_keep_both_changes(world: World) -> None:
    gate = asyncio.Event()
    original = world.images.generate

    async def slow_generate(*args, **kwargs):  # type: ignore[no-untyped-def]
        await gate.wait()
        return await original(*args, **kwargs)

    world.images.generate = slow_generate  # type: ignore[method-assign]
    director = FakeDirector({"t4": DirectedTurn((), (draft("mira", turn_id="t4"),))})

    render = asyncio.create_task(
        GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", "s1", 1)
    )
    await asyncio.sleep(0)  # the render has read its snapshot and is waiting on the model
    await DirectTurn(world.repo, director, SequentialIds("new")).execute("p1", turn(4))
    gate.set()
    await render

    saved = world.project()
    assert [s.number for s in saved.shots] == [1, 2, 3, 4]  # the turn's shot survived the render's save
    assert saved.panel("s1").has_render(1)  # and the render survived the turn's save


async def test_reference_drawn_for_an_outdated_description_is_not_attached(world: World) -> None:
    gate = asyncio.Event()
    original = world.images.generate

    async def slow_generate(*args, **kwargs):  # type: ignore[no-untyped-def]
        await gate.wait()
        return await original(*args, **kwargs)

    world.images.generate = slow_generate  # type: ignore[method-assign]
    task = asyncio.create_task(GenerateCharacterReference(world.repo, world.images, world.budget).execute("p1", "cat"))
    await asyncio.sleep(0)
    await ApproveCast(world.repo, world.jobs, world.ids).execute("p1", {"cat": "a tall black cat"})
    gate.set()
    cat = await task

    assert cat.reference is None
    assert world.project().bible.get("cat").reference is None


# ---- cast approval with corrections ----


async def test_approve_without_edits_approves(draft_world: World) -> None:
    p = draft_world.project()
    for c in p.bible.characters.values():
        p.bible.set_reference(c.id, MediaRef(f"r/{c.id}"))
    await draft_world.repo.save(p)

    review = await ApproveCast(draft_world.repo, draft_world.jobs, draft_world.ids).execute("p1", {"mira": ""})

    assert review.approved
    assert draft_world.project().bible.is_approved
    assert draft_world.jobs.jobs == []


async def test_approve_with_a_corrected_description_redraws_instead(world: World) -> None:
    review = await ApproveCast(world.repo, world.jobs, world.ids).execute(
        "p1", {"cat": "small grey kitten with glowing amber eyes", "mira": "Mira, now in a green raincoat"}
    )

    assert not review.approved
    assert review.redrawing == ("mira",)  # the cat's text did not change
    saved = world.project()
    assert not saved.bible.is_approved
    assert saved.bible.get("mira").reference is None
    assert saved.bible.get("cat").reference is not None
    [job] = world.jobs.jobs
    assert job.kind == GENERATE_CAST
    assert job.payload["character_ids"] == "mira"
    assert review.job_key == job.idempotency_key


async def test_approve_rejects_unknown_characters(world: World) -> None:
    with pytest.raises(UnknownCharacterError):
        await ApproveCast(world.repo, world.jobs, world.ids).execute("p1", {"dragon": "big"})


# ---- queued work ----


async def test_render_request_queues_the_next_revision_once(world: World) -> None:
    requests = RequestPanelRender(world.repo, world.jobs)
    first = await requests.execute("p1", "s1", "low")
    again = await requests.execute("p1", "s1", "low")

    assert (first.kind, first.shot_id, first.revision, first.enqueued) == (GENERATE_PANEL, "s1", 1, True)
    assert not again.enqueued  # same revision: deduplicated, never charged twice
    assert world.jobs.jobs[0].payload["quality"] == "low"

    await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", "s1", 1)
    final = await requests.execute("p1", "s1", "high")
    assert (final.revision, final.enqueued) == (2, True)


async def test_render_request_needs_an_approved_cast(draft_world: World) -> None:
    with pytest.raises(CastNotApprovedError):
        await RequestPanelRender(draft_world.repo, draft_world.jobs).execute("p1", "s1", "low")


async def test_edit_request_needs_a_rendered_panel_and_an_instruction(world: World) -> None:
    requests = RequestPanelEdit(world.repo, world.jobs)
    with pytest.raises(PanelNotReadyError):
        await requests.execute("p1", "s1", "make her coat red")
    await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", "s1", 1)
    with pytest.raises(InvalidValueError, match="instruction"):
        await requests.execute("p1", "s1", "   ")

    ticket = await requests.execute("p1", "s1", "make her coat red")
    assert (ticket.kind, ticket.revision) == (EDIT_PANEL, 1)
    assert not (await requests.execute("p1", "s1", " Make her coat red")).enqueued


async def test_cast_request_checks_characters_and_separates_regenerates(world: World) -> None:
    requests = RequestCastReferences(world.repo, world.jobs, world.ids)
    with pytest.raises(UnknownCharacterError):
        await requests.execute("p1", ["dragon"])
    a = await requests.execute("p1", ["mira"])
    b = await requests.execute("p1", ["mira"])
    assert a.enqueued
    assert b.enqueued  # a deliberate regenerate is a new job


async def test_edit_by_command_routes_through_the_director(world: World) -> None:
    await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", "s1", 1)
    director = FakeDirector()
    edit = EditPanelAppearance(world.repo, world.images, world.budget, world.jobs)

    panel = await EditPanelByCommand(world.repo, director, edit).execute("p1", "s1", "her coat is red now")

    assert panel.revision == 2
    assert director.calls == ["interpret_edit:her coat is red now"]
    [request] = world.images.edits
    assert request.image.key == "projects/p1/panels/s1/r1/image"
    assert "the raincoat and the hood" in request.prompt


async def test_cast_references_are_drawn_then_proposed(draft_world: World) -> None:
    events = RecordingPublisher()
    reference = GenerateCharacterReference(draft_world.repo, draft_world.images, draft_world.budget)

    drawn = await GenerateCastReferences(reference, events).execute("p1", ["mira", "cat"])

    assert [c.id for c in drawn] == ["mira", "cat"]
    [proposed] = events.of(CastProposed)
    assert isinstance(proposed, CastProposed)
    assert all(c.reference is not None for c in proposed.characters)


async def test_cast_proposes_what_worked_and_fails_the_job_for_the_rest(draft_world: World) -> None:
    events = RecordingPublisher()
    draft_world.images.fail_next = True
    reference = GenerateCharacterReference(draft_world.repo, draft_world.images, draft_world.budget)

    with pytest.raises(RuntimeError):
        await GenerateCastReferences(reference, events).execute("p1", ["mira", "cat"])
    [proposed] = events.of(CastProposed)
    assert isinstance(proposed, CastProposed)
    assert len(proposed.characters) == 1


# ---- live voice session ----


async def no_audio() -> AsyncIterator[bytes]:
    yield b"\x00\x00"


def session(repo: InMemoryProjectRepository, speech: FakeSpeechToText, director: FakeDirector):  # type: ignore[no-untyped-def]
    events, jobs = RecordingPublisher(), InMemoryJobQueue()
    cast = RequestCastReferences(repo, jobs, SequentialIds("n"))
    run = RunVoiceSession(
        speech,
        DirectTurn(repo, director, SequentialIds("shot")),
        CorrectTranscript(repo, director, SequentialIds("fix"), cast, events),
        cast,
        events,
        SequentialIds("s"),  # the session tag: turn ids become "s1-..."
        repo,
        InMemoryMediaStorage(),
    )
    return run, events, jobs


async def test_session_streams_transcript_shots_and_cast_in_order() -> None:
    p = project(approved=False, shots=0)
    p.bible.characters.clear()
    repo = InMemoryProjectRepository(p)
    t1 = TranscriptTurn("0", "An owl lands on the roof.", 0, 3000)
    speech = FakeSpeechToText(
        events=[TurnStarted("0", 0), PartialTranscript("An owl"), PartialTranscript("An owl lands"), TurnCompleted(t1)]
    )
    director = FakeDirector({"0": DirectedTurn((OWL,), (draft("owl", turn_id="0"),))})
    run, events, jobs = session(repo, speech, director)

    ended = await run.execute("p1", no_audio(), SpeechOptions(keywords=("Owl",)))

    assert [type(e) for _, e in events.events] == [
        TranscriptUpdated,
        TranscriptUpdated,
        TurnFinished,
        ShotCreated,
        SessionEnded,
    ]
    assert (ended.turns, ended.shots) == (1, 1)
    assert speech.options == SpeechOptions(keywords=("Owl",))
    [job] = jobs.jobs
    assert (job.kind, job.payload["character_ids"]) == (GENERATE_CAST, "owl")
    assert "owl" in repo.peek("p1").bible


async def test_session_reports_a_failed_turn_and_carries_on() -> None:
    repo = InMemoryProjectRepository(project(shots=0))
    t1, t2, blank = turn(1, text="first"), turn(2, text="second"), TranscriptTurn("3", "  ", 8000, 8100)
    speech = FakeSpeechToText(events=[TurnCompleted(t1), TurnCompleted(t2), TurnCompleted(blank)])

    class FlakyDirector(FakeDirector):
        async def direct_turn(self, turn: TranscriptTurn, project):  # type: ignore[no-untyped-def]
            if turn.id == "s1-t1":
                raise ModelTimeoutError("muse-spark-1.3")
            return await super().direct_turn(turn, project)

    director = FlakyDirector({"t2": DirectedTurn((), (draft("mira", turn_id="t2"),))})
    run, events, _ = session(repo, speech, director)

    ended = await run.execute("p1", no_audio(), SpeechOptions())

    [failure] = events.of(SessionFailed)
    assert isinstance(failure, SessionFailed)
    assert not failure.fatal
    assert "too long" in failure.message
    assert (ended.turns, ended.shots) == (3, 1)  # the blank turn is shown but not directed
    assert director.calls == ["t2"]


async def test_session_ends_with_a_fatal_error_when_transcription_fails() -> None:
    repo = InMemoryProjectRepository(project(shots=0))

    class BrokenSpeech(FakeSpeechToText):
        async def stream(self, audio, options):  # type: ignore[no-untyped-def]
            yield PartialTranscript("hello")
            raise ModelTimeoutError("muse-voice-transcribe-1.0")

    run, events, _ = session(repo, BrokenSpeech(), FakeDirector())
    await run.execute("p1", no_audio(), SpeechOptions())

    kinds = [type(e) for _, e in events.events]
    assert kinds == [TranscriptUpdated, SessionFailed, SessionEnded]
    [failure] = events.of(SessionFailed)
    assert isinstance(failure, SessionFailed)
    assert failure.fatal
