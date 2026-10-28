"""Rename, remove and merge characters after the fact ("Ember" turned out to be Pip)."""

import pytest

from frameteller.domain import CastStatus, InvalidValueError, MediaRef, Project, Size, UnknownCharacterError
from tests.builders import project


def drawn(shots: int = 3) -> Project:
    p = project(shots=shots)
    for s in p.shots:
        p.panel(s.id).record_render(1, MediaRef(f"projects/p1/panels/{s.id}/r1/image"), "resp", Size(1920, 1280))
    return p


def test_rename_keeps_the_sheet_and_the_approval() -> None:
    p = drawn()
    p.rename_character("cat", "Pip")
    assert p.bible.get("cat").name == "Pip"
    assert p.bible.get("cat").reference == MediaRef("refs/cat.webp")
    assert p.bible.status is CastStatus.APPROVED
    with pytest.raises(InvalidValueError):
        p.rename_character("cat", "  ")


def test_remove_drops_the_character_from_its_shots_and_keeps_their_action() -> None:
    p = drawn()  # shot 2 shows mira and cat
    changed = p.remove_character("cat")
    assert [s.id for s in changed] == ["s2"]
    assert p.shot("s2").character_ids == ("mira",)
    assert p.shot("s2").action == "action 2"
    assert "cat" not in p.bible
    assert p.panels["s2"].outdated
    assert not p.panels["s1"].outdated
    assert p.bible.status is CastStatus.APPROVED


def test_removing_the_last_character_returns_the_cast_to_draft() -> None:
    p = drawn()
    p.remove_character("cat")
    p.remove_character("mira")
    assert p.bible.status is CastStatus.DRAFT
    assert all(s.character_ids == () for s in p.shots)


def test_merge_rebinds_every_shot_without_duplicates() -> None:
    p = drawn()
    changed = p.merge_character("mira", into="cat")
    assert [s.id for s in changed] == ["s1", "s2", "s3"]
    assert [s.character_ids for s in p.shots] == [("cat",), ("cat",), ("cat",)]  # shot 2 had both
    assert "mira" not in p.bible
    assert all(p.panels[s.id].outdated for s in p.shots)


def test_a_new_render_clears_outdated() -> None:
    p = drawn()
    p.remove_character("cat")
    p.panels["s2"].record_render(2, MediaRef("projects/p1/panels/s2/r2/image"), "resp2", Size(1920, 1280))
    assert not p.panels["s2"].outdated


def test_merge_needs_two_known_characters() -> None:
    p = drawn()
    with pytest.raises(InvalidValueError):
        p.merge_character("cat", into="cat")
    with pytest.raises(UnknownCharacterError):
        p.merge_character("cat", into="owl")
    with pytest.raises(UnknownCharacterError):
        p.remove_character("owl")
    assert "cat" in p.bible  # nothing changed on failure


def test_undrawn_panels_are_not_marked() -> None:
    p = project()
    p.panel("s2")  # pending, never drawn
    p.remove_character("cat")
    assert not p.panels["s2"].outdated
