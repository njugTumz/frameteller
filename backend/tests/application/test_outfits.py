"""The tester's costume story (ADR 0018): once Wren puts on her farmer costume, every later panel draws her in it."""

import asyncio
from dataclasses import replace

import pytest

from frameteller.application.events import CastProposed, ShotCreated, ShotUpdated
from frameteller.application.ports import DirectedTurn, LookChange, ShotDraft
from frameteller.application.use_cases import (
    ApproveCast,
    CorrectTranscript,
    DirectTurn,
    GenerateCastReferences,
    GenerateCharacterReference,
    GeneratePanel,
    RequestCastReferences,
)
from frameteller.application.use_cases.story_director import StoryDirector, TranscriptCorrection
from frameteller.domain import EVERYDAY, Framing, MediaRef, Project, TranscriptTurn
from tests.builders import COSTUME, DAD, FARMER, WREN, costume_project, costume_turn
from tests.fakes import (
    PANEL_SIZE,
    FakeDirector,
    FakeImageGeneration,
    InMemoryJobQueue,
    InMemoryMediaStorage,
    InMemoryProjectRepository,
    RecordingBudget,
    RecordingPublisher,
    SequentialIds,
)

PUTS_ON = LookChange("wren", FARMER.id, FARMER.label, FARMER.clothes, 2)


def draft(action: str, *characters: str) -> ShotDraft:
    return ShotDraft(Framing.MEDIUM, characters, "a family house on Halloween", action, "", ("?",), 1)


def scripted() -> FakeDirector:
    """What Muse Spark returns for each paragraph: one shot each; paragraph 2 records the costume."""
    cast = {1: ("wren", "dad"), 3: ("wren", "dad")}
    turns = {
        f"t{n}": DirectedTurn((WREN, DAD) if n == 1 else (), (draft(COSTUME[n - 1], *cast.get(n, ("wren",))),))
        for n in range(1, 7)
    }
    turns["t2"] = replace(turns["t2"], looks=(PUTS_ON,))
    return FakeDirector(turns)


IDS = SequentialIds("shot")


async def tell(repo: InMemoryProjectRepository, director: FakeDirector, *numbers: int) -> list[str]:
    looks: list[str] = []
    direct = DirectTurn(repo, director, IDS)
    for n in numbers:
        looks += (await direct.execute("p1", costume_turn(n))).new_looks
    return looks


async def drawn_cast(repo: InMemoryProjectRepository) -> None:
    def apply(p: Project) -> None:
        p.bible.set_reference("wren", MediaRef("refs/wren.webp"))
        p.bible.set_reference("dad", MediaRef("refs/dad.webp"))

    await repo.update("p1", apply)


async def test_the_whole_story_keeps_the_costume_from_shot_2_on() -> None:
    repo = InMemoryProjectRepository(Project(id="p1"))
    director = scripted()
    assert await tell(repo, director, 1) == []
    await drawn_cast(repo)
    assert await tell(repo, director, 2, 3, 4, 5, 6) == ["wren/farmer_costume"]

    p = repo.peek("p1")
    worn = [(look.id if (look := p.look_in(s.id, "wren")) else EVERYDAY) for s in p.shots]
    assert worn == [EVERYDAY, *["farmer_costume"] * 5]
    assert p.bible.get("wren").look("farmer_costume").clothes == FARMER.clothes


async def test_every_panel_after_the_costume_is_drawn_from_the_costume_sheet() -> None:
    storage = InMemoryMediaStorage()
    images = FakeImageGeneration(storage)
    p = costume_project(looks=False)
    p.change_outfit("wren", FARMER, "s2")
    repo = InMemoryProjectRepository(p)
    budget, jobs, events = RecordingBudget(), InMemoryJobQueue(), RecordingPublisher()
    reference = GenerateCharacterReference(repo, images, budget)

    await GenerateCastReferences(reference, events, repo).execute("p1", ["wren/farmer_costume"])
    look_sheet = repo.peek("p1").bible.get("wren").look("farmer_costume").reference
    assert look_sheet == MediaRef("projects/p1/characters/wren/looks/farmer_costume")
    [sheet] = images.generated
    assert sheet.references == (MediaRef("refs/wren.webp"),)  # the same girl, from her everyday sheet
    assert "now they wear blue denim overalls over a white shirt" in sheet.prompt
    assert "same face, hair, skin, build" in sheet.prompt
    await ApproveCast(repo, jobs, SequentialIds("j")).execute("p1")

    draw = GeneratePanel(repo, images, budget, jobs)
    for s in repo.peek("p1").shots:
        await draw.execute("p1", s.id, 1)
    panels = images.generated[1:]
    assert [r.references[0] for r in panels] == [MediaRef("refs/wren.webp")] + [look_sheet] * 5
    assert "purple pyjamas" in panels[0].prompt
    assert all("wears the farmer costume: blue denim overalls" in r.prompt for r in panels[1:])


async def test_the_director_turn_queues_the_costume_sheet_and_outdates_drawn_panels() -> None:
    p = costume_project(looks=False)
    p.shots, p.turns = p.shots[:1], p.turns[:1]
    p.panel("s1").record_render(1, MediaRef("panels/s1.webp"), "resp", PANEL_SIZE)
    repo, events, jobs = InMemoryProjectRepository(p), RecordingPublisher(), InMemoryJobQueue()
    director = scripted()
    # A reveal: paragraph 2 says she had already changed, from shot 1 on.
    director.turns["t2"] = replace(director.turns["t2"], looks=(replace(PUTS_ON, from_shot=1),))
    cast = RequestCastReferences(repo, jobs, SequentialIds("c"))
    story = StoryDirector(
        DirectTurn(repo, director, SequentialIds("new")),
        CorrectTranscript(repo, director, SequentialIds("x"), cast, events),
        cast,
        events,
    )
    work: asyncio.Queue[TranscriptTurn | TranscriptCorrection | None] = asyncio.Queue()
    for item in (costume_turn(2), None):
        work.put_nowait(item)

    assert await story.run("p1", work) == 1
    [job] = jobs.jobs
    assert job.payload["character_ids"] == "wren/farmer_costume"
    assert repo.peek("p1").panels["s1"].outdated
    assert [e.shot.id for e in events.of(ShotUpdated) if isinstance(e, ShotUpdated)] == ["s1"]


async def test_a_change_from_a_shot_that_was_never_added_is_skipped() -> None:
    repo = InMemoryProjectRepository(Project(id="p1"))
    director = scripted()
    director.turns["t2"] = replace(director.turns["t2"], looks=(replace(PUTS_ON, from_shot=9),))
    await tell(repo, director, 1)
    await drawn_cast(repo)
    assert await tell(repo, director, 2) == []
    assert repo.peek("p1").outfits == []


async def test_editing_a_looks_clothes_redraws_only_that_sheet() -> None:
    repo, jobs = InMemoryProjectRepository(costume_project()), InMemoryJobQueue()
    review = await ApproveCast(repo, jobs, SequentialIds("j")).execute(
        "p1", {"wren/farmer_costume": "green overalls, a straw hat, brown boots"}
    )
    assert review.redrawing == ("wren/farmer_costume",)
    [job] = jobs.jobs
    assert job.payload["character_ids"] == "wren/farmer_costume"
    wren = repo.peek("p1").bible.get("wren")
    assert wren.reference == MediaRef("refs/wren.webp")
    assert wren.look("farmer_costume").reference is None


async def test_a_new_everyday_description_redraws_the_costume_too() -> None:
    storage = InMemoryMediaStorage()
    images, events = FakeImageGeneration(storage), RecordingPublisher()
    repo = InMemoryProjectRepository(costume_project())
    await ApproveCast(repo, InMemoryJobQueue(), SequentialIds("j")).execute(
        "p1", {"wren": "human little girl, red curly hair, purple pyjamas"}
    )
    reference = GenerateCharacterReference(repo, images, RecordingBudget())
    await GenerateCastReferences(reference, events, repo).execute("p1", ["wren"])
    assert [r.references for r in images.generated] == [(), (MediaRef("projects/p1/characters/wren/reference"),)]
    wren = repo.peek("p1").bible.get("wren")
    assert wren.look("farmer_costume").reference == MediaRef("projects/p1/characters/wren/looks/farmer_costume")
    [proposed] = events.of(CastProposed)
    assert isinstance(proposed, CastProposed)
    assert [c.id for c in proposed.characters] == ["wren"]


async def test_a_refused_costume_sheet_is_reported_for_that_look() -> None:
    storage = InMemoryMediaStorage()
    images = FakeImageGeneration(storage)
    images.fail_next = True
    repo = InMemoryProjectRepository(costume_project())
    with pytest.raises(RuntimeError):
        await GenerateCharacterReference(repo, images, RecordingBudget()).execute(
            "p1", "wren", look_id="farmer_costume"
        )


async def test_try_again_on_a_look_checks_it_exists() -> None:
    repo, jobs = InMemoryProjectRepository(costume_project()), InMemoryJobQueue()
    request = RequestCastReferences(repo, jobs, SequentialIds("c"))
    ticket = await request.execute("p1", ["wren/farmer_costume"])
    assert ticket.enqueued
    with pytest.raises(Exception, match="no look"):
        await request.execute("p1", ["wren/witch_costume"])


async def test_a_correction_says_again_who_changes_clothes() -> None:
    repo, events, jobs = InMemoryProjectRepository(costume_project()), RecordingPublisher(), InMemoryJobQueue()
    director = scripted()
    director.turns["t2"] = replace(director.turns["t2"], looks=())  # the corrected words drop the costume
    cast = RequestCastReferences(repo, jobs, SequentialIds("c"))
    await CorrectTranscript(repo, director, SequentialIds("x"), cast, events).execute(
        "p1", "t2", "In her bedroom, Wren looks in the mirror and grins."
    )
    p = repo.peek("p1")
    assert p.outfits == []
    assert all(p.look_in(s.id, "wren") is None for s in p.shots)

    director.turns["t2"] = replace(director.turns["t2"], looks=(replace(PUTS_ON, from_shot=6),))
    await CorrectTranscript(repo, director, SequentialIds("y"), cast, events).execute("p1", "t2", COSTUME[1])
    p = repo.peek("p1")
    [change] = p.outfits
    assert p.shot(change.from_shot_id).number == 2  # the corrected shot took shot 2's place
    assert p.look_in(p.shots[-1].id, "wren") is not None


async def test_shot_events_say_who_wears_which_look() -> None:
    repo, events, jobs = InMemoryProjectRepository(Project(id="p1")), RecordingPublisher(), InMemoryJobQueue()
    director = scripted()
    cast = RequestCastReferences(repo, jobs, SequentialIds("c"))
    story = StoryDirector(
        DirectTurn(repo, director, SequentialIds("e")),
        CorrectTranscript(repo, director, SequentialIds("x"), cast, events),
        cast,
        events,
    )
    work: asyncio.Queue[TranscriptTurn | TranscriptCorrection | None] = asyncio.Queue()
    for item in (costume_turn(1), costume_turn(2), costume_turn(3), None):
        work.put_nowait(item)
    await story.run("p1", work)
    created = [e for e in events.of(ShotCreated) if isinstance(e, ShotCreated)]
    assert [e.looks for e in created] == [(), (("wren", "farmer_costume"),), (("wren", "farmer_costume"),)]
