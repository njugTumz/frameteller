from dataclasses import replace

import pytest

from frameteller.domain import (
    CastNotApprovedError,
    Framing,
    InvalidValueError,
    Project,
    Shot,
    ShotOrderError,
    TranscriptTurn,
    UnknownCharacterError,
    UnknownShotError,
    UnknownTurnError,
)
from tests.builders import CAT, MIRA, project, shot, turn


def test_shots_may_only_reference_characters_in_the_bible() -> None:
    p = project(shots=0)
    p.add_turn(turn(1))
    with pytest.raises(UnknownCharacterError, match="dragon"):
        p.append_shots([shot(1, "mira", "dragon")])
    assert p.shots == []


def test_appended_shots_must_continue_the_numbering() -> None:
    p = project(shots=2)
    p.add_turn(turn(3))
    with pytest.raises(ShotOrderError):
        p.append_shots([shot(4, "mira", turn_ids=("t3",))])
    p.append_shots([shot(3, "mira")])
    assert [s.number for s in p.shots] == [1, 2, 3]


def test_shots_must_cite_known_turns() -> None:
    p = project(shots=0)
    with pytest.raises(ShotOrderError, match="t9"):
        p.append_shots([shot(1, "mira", turn_ids=("t9",))])


def test_reorder_renumbers_contiguously() -> None:
    p = project(shots=4)
    p.reorder_shots(["s4", "s2", "s3", "s1"])  # swap shots 1 and 4
    assert [s.id for s in p.shots] == ["s4", "s2", "s3", "s1"]
    assert [s.number for s in p.shots] == [1, 2, 3, 4]


@pytest.mark.parametrize("order", [["s1", "s2"], ["s1", "s2", "s3", "s3"], ["s1", "s2", "s9"]])
def test_reorder_must_be_a_permutation(order: list[str]) -> None:
    p = project(shots=3)
    with pytest.raises(ShotOrderError):
        p.reorder_shots(order)
    assert [s.id for s in p.shots] == ["s1", "s2", "s3"]


def test_panels_cannot_be_drawn_until_cast_is_approved() -> None:
    with pytest.raises(CastNotApprovedError):
        project(approved=False).require_cast_approved()
    project(approved=True).require_cast_approved()


def test_unknown_shot() -> None:
    p = project()
    with pytest.raises(UnknownShotError):
        p.shot("nope")
    with pytest.raises(UnknownShotError):
        p.panel("nope")


def test_panel_is_created_on_first_access() -> None:
    p = project()
    assert p.panel("s1") is p.panel("s1")
    assert p.panel("s1").revision == 0


def test_duplicate_turn_is_ignored() -> None:
    p = Project(id="p")
    p.add_turn(turn(1))
    p.add_turn(turn(1))
    assert len(p.turns) == 1


def test_upsert_character_goes_through_the_bible() -> None:
    p = Project(id="p")
    p.upsert_character(MIRA)
    p.upsert_character(CAT)
    assert set(p.bible.characters) == {"mira", "cat"}


def test_turn_timing_must_be_ordered() -> None:
    assert TranscriptTurn("t", "x", 1000, 3500).duration_ms == 2500
    with pytest.raises(InvalidValueError):
        TranscriptTurn("t", "x", 3000, 1000)
    with pytest.raises(InvalidValueError):
        TranscriptTurn("t", "x", -1, 10)


@pytest.mark.parametrize(("number", "duration", "turns"), [(0, 1000, ("t1",)), (1, 0, ("t1",)), (1, 1000, ())])
def test_shot_values_are_validated(number: int, duration: int, turns: tuple[str, ...]) -> None:
    with pytest.raises(InvalidValueError):
        Shot("s", number, Framing.WIDE, (), "alley", "rain", "", turns, duration)


def test_correcting_a_turn_keeps_its_timing() -> None:
    p = project()
    fixed = p.correct_turn("t2", "  She kneels by the crate. ")
    assert (fixed.text, fixed.start_ms, fixed.end_ms) == ("She kneels by the crate.", 4000, 8000)
    assert p.turn("t2") == fixed
    with pytest.raises(UnknownTurnError):
        p.correct_turn("t9", "text")
    with pytest.raises(InvalidValueError):
        p.correct_turn("t2", "  ")


def test_replacing_a_turns_shots_keeps_their_place_and_drops_their_panels() -> None:
    p = project()
    p.panel("s2")
    new = [replace(shot(1, "cat", turn_ids=("t2",)), id="n1"), replace(shot(1, "mira", turn_ids=("t2",)), id="n2")]
    placed = p.replace_shots(["s2"], new)
    assert [(s.id, s.number) for s in p.shots] == [("s1", 1), ("n1", 2), ("n2", 3), ("s3", 4)]
    assert [s.number for s in placed] == [2, 3]
    assert "s2" not in p.panels
    assert p.shots_from_turn("t2") == placed


def test_replacing_with_nothing_old_appends_and_unknown_ids_fail() -> None:
    p = project()
    p.replace_shots([], [replace(shot(1, "mira", turn_ids=("t1",)), id="n1")])
    assert [s.id for s in p.shots] == ["s1", "s2", "s3", "n1"]
    with pytest.raises(UnknownShotError):
        p.replace_shots(["s9"], [])
    with pytest.raises(ShotOrderError):
        p.replace_shots(["s1"], [replace(shot(1, "mira", turn_ids=("t9",)), id="n2")])
