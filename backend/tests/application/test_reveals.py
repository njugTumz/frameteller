"""Reveals: a later turn says who or what an earlier, vague shot showed (the lighthouse story)."""

from dataclasses import replace

from frameteller.application.events import ShotCreated, ShotUpdated
from frameteller.application.ports import DirectedTurn, ShotDraft, ShotRevision, SpeechOptions, TurnCompleted
from frameteller.application.use_cases import DirectTurn
from frameteller.application.use_cases.direct_turn import REVEAL_WINDOW
from frameteller.domain import Framing, MediaRef, Project, Size, TranscriptTurn
from tests.application.test_beats import CHUNK, Session
from tests.builders import ADA, EMBER, PIP, lighthouse_turn, shot
from tests.fakes import LISTEN, FakeDirector, InMemoryProjectRepository, ScriptedSpeech, SequentialIds


def draft(action: str, *characters: str, framing: Framing = Framing.MEDIUM) -> ShotDraft:
    return ShotDraft(framing, characters, "a lighthouse in a storm", action, "", ("?",), 1)


def story_so_far(*, guessed_ember: bool) -> Project:
    """Turns 1-3 directed: shot 3 is the window, with a butterfly guessed for it or with nobody."""
    p = Project(id="p1", title="The lighthouse fox")
    p.upsert_character(ADA)
    if guessed_ember:
        p.upsert_character(EMBER)
    p.bible.set_reference("ada", MediaRef("refs/ada.webp"))
    for n in (1, 2, 3):
        p.add_turn(lighthouse_turn(n))
    p.append_shots(
        [
            shot(1),
            shot(2, "ada"),
            shot(3, "ember") if guessed_ember else shot(3),
        ]
    )
    p.panel("s3").record_render(1, MediaRef("projects/p1/panels/s3/r1/image"), "resp", Size(1920, 1280))
    return p


REVEAL = DirectedTurn(
    (PIP,),
    (draft("Ada opens the window and Pip tumbles inside", "ada", "pip"),),
    (ShotRevision("s3", ("pip",), "Pip, small and orange, flaps against the window glass in the wind"),),
)


async def test_a_reveal_revises_the_vague_shot_and_marks_its_panel() -> None:
    repo = InMemoryProjectRepository(story_so_far(guessed_ember=False))
    directed = await DirectTurn(repo, FakeDirector({"t4": REVEAL}), SequentialIds("n")).execute(
        "p1", lighthouse_turn(4)
    )

    p = repo.peek("p1")
    assert [s.id for s in directed.revised] == ["s3"]
    assert p.shot("s3").character_ids == ("pip",)
    assert p.shot("s3").action.startswith("Pip, small and orange")
    assert p.shot("s3").duration_ms == 4000  # timing never changes
    assert p.panels["s3"].outdated
    assert [s.number for s in p.shots] == [1, 2, 3, 4]
    assert "pip" in p.bible


async def test_a_guess_the_reveal_replaced_leaves_the_cast() -> None:
    repo = InMemoryProjectRepository(story_so_far(guessed_ember=True))
    directed = await DirectTurn(repo, FakeDirector({"t4": REVEAL}), SequentialIds("n")).execute(
        "p1", lighthouse_turn(4)
    )

    assert directed.dropped_character_ids == ("ember",)
    p = repo.peek("p1")
    assert "ember" not in p.bible
    assert sorted(p.bible.characters) == ["ada", "pip"]


async def test_a_character_still_in_another_shot_stays() -> None:
    p = story_so_far(guessed_ember=True)
    p.shots[0] = replace(p.shots[0], character_ids=("ember",))
    repo = InMemoryProjectRepository(p)
    directed = await DirectTurn(repo, FakeDirector({"t4": REVEAL}), SequentialIds("n")).execute(
        "p1", lighthouse_turn(4)
    )
    assert directed.dropped_character_ids == ()


async def test_only_the_latest_shots_can_be_revised() -> None:
    p = story_so_far(guessed_ember=False)
    for n in (4, 5, 6):
        p.add_turn(lighthouse_turn(n))
    p.append_shots([shot(n, "ada", turn_ids=(f"t{n}",)) for n in (4, 5, 6)])
    assert REVEAL_WINDOW == 3
    old = DirectedTurn((PIP,), (draft("Ada smiles", "ada"),), (ShotRevision("s3", ("pip",), "too late"),))
    repo = InMemoryProjectRepository(p)
    turn7 = TranscriptTurn("t7", "They sleep.", 48000, 52000)
    directed = await DirectTurn(repo, FakeDirector({"t7": old}), SequentialIds("n")).execute("p1", turn7)
    assert directed.revised == ()
    assert repo.peek("p1").shot("s3").character_ids == ()


async def test_the_live_session_sends_shot_updated_before_the_new_shot() -> None:
    speech = ScriptedSpeech([TurnCompleted(lighthouse_turn(4)), LISTEN])
    s = Session(speech, FakeDirector({"t4": REVEAL}), story=story_so_far(guessed_ember=True))

    await s.run.execute("p1", speech.paced(CHUNK), SpeechOptions())

    kinds = [type(e).__name__ for _, e in s.events.events if isinstance(e, ShotUpdated | ShotCreated)]
    assert kinds == ["ShotUpdated", "ShotCreated"]
    [updated] = s.events.of(ShotUpdated)
    assert isinstance(updated, ShotUpdated)
    assert updated.shot.character_ids == ("pip",)
