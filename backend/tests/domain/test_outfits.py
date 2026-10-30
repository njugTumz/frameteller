"""Outfits (ADR 0018): a costume put on in one shot stays on in every later shot, with its own sheet."""

import pytest

from frameteller.domain import EVERYDAY, InvalidValueError, Look, MediaRef, MissingReferenceError, sheet_target
from frameteller.domain.characters import split_target
from tests.builders import FARMER, costume_project, shot
from tests.fakes import PANEL_SIZE


def test_the_costume_carries_forward_from_the_shot_it_is_put_on() -> None:
    p = costume_project()
    worn = [(s.number, (look.id if (look := p.look_in(s.id, "wren")) else EVERYDAY)) for s in p.shots]
    assert worn == [
        (1, "everyday"),
        (2, "farmer_costume"),
        (3, "farmer_costume"),
        (4, "farmer_costume"),
        (5, "farmer_costume"),
        (6, "farmer_costume"),
    ]
    assert p.look_in("s4", "dad") is None  # only Wren changed


def test_each_shot_casts_her_in_the_look_she_wears_with_its_sheet() -> None:
    p = costume_project()
    (before,) = (c for c in p.cast_in("s1") if c.id == "wren")
    (after,) = p.cast_in("s5")
    assert before.reference == MediaRef("refs/wren.webp")
    assert "purple pyjamas" in before.canonical_description
    assert "overalls" not in before.canonical_description
    assert after.reference == MediaRef("refs/wren-farmer.webp")
    assert after.canonical_description.endswith(
        "In this shot Wren wears the farmer costume: blue denim overalls over a white shirt, a red bandana around "
        "her neck, brown cowgirl boots, instead of any clothes described before"
    )


def test_changing_back_and_into_the_costume_again() -> None:
    p = costume_project()
    p.change_outfit("wren", None, "s6")  # back home, out of the costume
    assert p.look_in("s5", "wren") == p.bible.get("wren").look("farmer_costume")
    assert p.look_in("s6", "wren") is None
    p.change_outfit("wren", FARMER, "s6")  # the same shot again: the later change wins
    assert p.look_in("s6", "wren") is not None
    assert len(p.outfits) == 2


def test_a_new_look_needs_its_sheet_before_the_cast_is_approved_again() -> None:
    p = costume_project(looks=False)
    assert p.bible.is_approved
    p.change_outfit("wren", FARMER, "s2")
    assert not p.bible.is_approved
    with pytest.raises(MissingReferenceError, match="wren/farmer_costume"):
        p.bible.approve()
    p.bible.set_look_reference("wren", "farmer_costume", MediaRef("refs/wren-farmer.webp"))
    p.bible.approve()


def test_a_late_costume_outdates_the_panels_already_drawn_in_everyday_clothes() -> None:
    p = costume_project(looks=False)
    for s in p.shots:
        p.panel(s.id).record_render(1, MediaRef(f"panels/{s.id}.webp"), f"resp_{s.id}", PANEL_SIZE)
    changed = p.change_outfit("wren", FARMER, "s2")
    assert changed == ["s2", "s3", "s4", "s5", "s6"]
    assert [p.panels[s.id].outdated for s in p.shots] == [False, True, True, True, True, True]


def test_new_clothes_for_a_look_drop_its_sheet_and_outdate_its_panels() -> None:
    p = costume_project()
    p.panel("s4").record_render(1, MediaRef("panels/s4.webp"), "resp_s4", PANEL_SIZE)
    changed = p.restyle_look("wren", "farmer_costume", "green overalls, straw hat, white shirt, brown boots")
    assert "s4" in changed
    assert p.panels["s4"].outdated
    assert p.bible.get("wren").look("farmer_costume").reference is None
    assert not p.bible.is_approved


def test_a_new_everyday_description_drops_the_look_sheets_drawn_from_it() -> None:
    p = costume_project()
    wren = p.bible.get("wren")
    p.upsert_character(wren.__class__(wren.id, wren.name, "human little girl, red curly hair", None, wren.looks))
    assert p.bible.get("wren").look("farmer_costume").reference is None
    assert p.bible.get("wren").looks[0].clothes == FARMER.clothes  # the look itself stays


def test_outfit_changes_move_with_their_shot_and_leave_with_their_character() -> None:
    p = costume_project()
    p.delete_shot("s2")  # the shot she put it on: the costume now starts at the next shot
    assert [o.from_shot_id for o in p.outfits] == ["s3"]
    assert p.look_in("s3", "wren") is not None
    p.remove_character("wren")
    assert p.outfits == []


def test_an_outfit_change_needs_a_shot_and_a_look_its_rules() -> None:
    p = costume_project()
    with pytest.raises(Exception, match="no shot"):
        p.change_outfit("wren", FARMER, "s99")
    with pytest.raises(InvalidValueError):
        Look(EVERYDAY, "Everyday", "pyjamas")
    with pytest.raises(InvalidValueError):
        Look("Farmer Costume", "Farmer", "overalls")
    with pytest.raises(InvalidValueError):
        Look("farmer", "", "overalls")


def test_sheet_targets_name_a_character_or_one_of_its_looks() -> None:
    assert sheet_target("wren") == sheet_target("wren", EVERYDAY) == "wren"
    assert sheet_target("wren", "farmer_costume") == "wren/farmer_costume"
    assert split_target("wren/farmer_costume") == ("wren", "farmer_costume")
    assert split_target("wren") == ("wren", None)


def test_a_shot_without_the_character_is_unaffected() -> None:
    p = costume_project()
    p.append_shots([shot(7, "dad", turn_ids=("t6",))])
    assert [c.id for c in p.cast_in("s7")] == ["dad"]
    assert p.look_in("s7", "wren") is not None  # she would still wear it, if she were in it


COWGIRL = Look(
    "cowgirl_costume", "Cowgirl farmer costume", "denim overalls over a white shirt, red bandana, cowgirl boots"
)


def test_a_costume_the_director_replaced_at_the_same_shot_is_hidden_and_needs_no_sheet() -> None:
    p = costume_project(looks=False)
    p.change_outfit("wren", FARMER, "s2")
    p.change_outfit("wren", COWGIRL, "s2")  # the same shot: the later change wins, Farmer is worn nowhere
    assert p.worn_looks() == {"wren/cowgirl_costume"}
    assert [lk.id for lk in p.shown(p.bible.get("wren")).looks] == ["cowgirl_costume"]
    with pytest.raises(MissingReferenceError, match="wren/cowgirl_costume"):
        p.approve_cast()
    p.bible.set_look_reference("wren", "cowgirl_costume", MediaRef("refs/wren-cowgirl.webp"))
    p.approve_cast()  # no sheet for the unworn Farmer costume
    assert p.bible.is_approved


def test_an_unworn_costume_keeps_an_approved_cast_approved_and_comes_back_with_its_sheet() -> None:
    p = costume_project()  # Farmer from shot 2, drawn and approved
    p.change_outfit("wren", COWGIRL, "s2")
    assert p.worn_looks() == {"wren/cowgirl_costume"}
    assert not p.bible.is_approved  # the worn Cowgirl costume has no sheet yet
    p.bible.set_look_reference("wren", "cowgirl_costume", MediaRef("refs/wren-cowgirl.webp"))
    p.approve_cast()

    p.change_outfit("wren", FARMER, "s2")  # a correction: Farmer after all, with the sheet it kept
    assert p.worn_looks() == {"wren/farmer_costume"}
    assert p.bible.get("wren").look("farmer_costume").reference == MediaRef("refs/wren-farmer.webp")
    assert p.bible.is_approved


def test_a_costume_whose_shots_are_all_deleted_is_hidden() -> None:
    p = costume_project()
    p.change_outfit("wren", None, "s3")  # only shot 2 shows the costume
    p.delete_shot("s2")
    assert "wren/farmer_costume" not in p.worn_looks()
    assert p.shown(p.bible.get("wren")).looks == ()
    assert p.bible.get("wren").look("farmer_costume").reference is not None  # kept, in case it comes back


def test_a_worn_look_without_a_sheet_sends_the_cast_back_to_draft() -> None:
    p = costume_project(looks=False)
    p.change_outfit("wren", FARMER, "s6")
    assert not p.bible.is_approved
