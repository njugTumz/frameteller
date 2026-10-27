import pytest

from frameteller.application.ports import DirectedTurn, ShotDraft
from frameteller.application.use_cases import ApproveCast, BuildCharacterBible, DirectTurn, ReorderShots
from frameteller.domain import (
    CastStatus,
    Character,
    Framing,
    MediaRef,
    MissingReferenceError,
    ShotOrderError,
    UnknownCharacterError,
)
from tests.builders import CAT, MIRA, project, turn
from tests.fakes import FakeDirector, InMemoryProjectRepository, SequentialIds

OWL = Character("owl", "Owl", "a small brown owl with round spectacles")


def draft(*characters: str, turn_id: str = "t4") -> ShotDraft:
    return ShotDraft(Framing.WIDE, tuple(characters), "rooftop", "the owl lands", "", (turn_id,), 4000)


async def test_direct_turn_appends_numbered_shots_and_new_characters() -> None:
    repo = InMemoryProjectRepository(project(shots=3))
    director = FakeDirector({"t4": DirectedTurn((OWL,), (draft("owl"), draft("mira", "owl")))})
    shots = await DirectTurn(repo, director, SequentialIds("new")).execute("p1", turn(4))

    assert [(s.id, s.number) for s in shots] == [("new1", 4), ("new2", 5)]
    saved = repo.peek("p1")
    assert [s.number for s in saved.shots] == [1, 2, 3, 4, 5]
    assert "owl" in saved.bible
    assert saved.bible.status is CastStatus.DRAFT  # a new character needs approval (ADR 0004)
    assert director.calls == ["t4"]


async def test_direct_turn_rejects_shots_with_unknown_characters() -> None:
    repo = InMemoryProjectRepository(project(shots=3))
    director = FakeDirector({"t4": DirectedTurn((), (draft("dragon"),))})
    with pytest.raises(UnknownCharacterError):
        await DirectTurn(repo, director, SequentialIds()).execute("p1", turn(4))
    assert len(repo.peek("p1").shots) == 3


async def test_build_character_bible_adds_characters() -> None:
    p = project(approved=False, shots=0)
    p.bible.characters.clear()
    repo = InMemoryProjectRepository(p)
    bible = await BuildCharacterBible(repo, FakeDirector(characters=[MIRA, CAT])).execute("p1")
    assert set(bible.characters) == {"mira", "cat"}
    assert set(repo.peek("p1").bible.characters) == {"mira", "cat"}


async def test_approve_cast() -> None:
    p = project(approved=False)
    for c in p.bible.characters.values():
        p.bible.set_reference(c.id, MediaRef(f"r/{c.id}"))
    repo = InMemoryProjectRepository(p)
    await ApproveCast(repo).execute("p1")
    assert repo.peek("p1").bible.is_approved


async def test_approve_cast_without_references_fails() -> None:
    repo = InMemoryProjectRepository(project(approved=False))
    with pytest.raises(MissingReferenceError):
        await ApproveCast(repo).execute("p1")
    assert not repo.peek("p1").bible.is_approved


async def test_reorder_shots_saves_new_order() -> None:
    repo = InMemoryProjectRepository(project(shots=4))
    shots = await ReorderShots(repo).execute("p1", ["s1", "s4", "s3", "s2"])  # swap shots 2 and 4
    assert [(s.id, s.number) for s in shots] == [("s1", 1), ("s4", 2), ("s3", 3), ("s2", 4)]
    assert [s.id for s in repo.peek("p1").shots] == ["s1", "s4", "s3", "s2"]


async def test_reorder_shots_rejects_partial_order() -> None:
    repo = InMemoryProjectRepository(project(shots=4))
    with pytest.raises(ShotOrderError):
        await ReorderShots(repo).execute("p1", ["s1", "s4"])
