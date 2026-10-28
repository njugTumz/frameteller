from dataclasses import replace

import pytest

from frameteller.application.prompts import STYLES, edit_prompt, panel_prompt, reference_prompt
from frameteller.domain import MediaRef, PanelStyle
from tests.builders import CAT, MIRA, shot


def test_edit_prompt_names_every_part_listed() -> None:
    parts = ["hood", "sleeves", "pockets", "hem"]
    prompt = edit_prompt("make it red", "raincoat", parts)
    for part in parts:
        assert f"the {part}" in prompt
    assert prompt.startswith(
        "Edit the raincoat, including the hood, the sleeves, the pockets and the hem: make it red."
    )
    assert "every part listed" in prompt


def test_edit_prompt_with_one_part_and_with_none() -> None:
    assert "including the hood:" in edit_prompt("make it red", "raincoat", ["hood"])
    assert edit_prompt("make it red.", "raincoat", []).startswith("Edit the raincoat: make it red.")


def test_edit_prompt_ignores_blank_parts() -> None:
    assert "the  " not in edit_prompt("make it red", "raincoat", ["hood", " ", ""])


def test_edit_prompt_keeps_geometry() -> None:
    assert "position" in edit_prompt("make it red", "raincoat", ["hood"])


@pytest.mark.parametrize(("change", "target"), [("", "raincoat"), ("make it red", " ")])
def test_edit_prompt_needs_change_and_target(change: str, target: str) -> None:
    with pytest.raises(ValueError, match="change and a target"):
        edit_prompt(change, target, [])


def test_panel_prompt_includes_cast_and_framing() -> None:
    prompt = panel_prompt(shot(1, "mira", "cat"), [MIRA, CAT])
    assert "medium framing" in prompt
    assert MIRA.canonical_description in prompt
    assert CAT.canonical_description in prompt


def test_panel_prompt_names_the_sheets_in_order_and_forbids_additions() -> None:
    mira = replace(MIRA, reference=MediaRef("refs/mira.webp"))
    cat = replace(CAT, reference=MediaRef("refs/cat.webp"))
    prompt = panel_prompt(shot(1, "mira", "cat"), [mira, cat])
    assert "reference sheets show, in order: Mira, Grey Cat" in prompt
    assert "exactly as in their reference sheet" in prompt
    assert "no added clothing, accessories or change of style" in prompt


def test_panel_prompt_without_sheets_attaches_none() -> None:
    assert "reference sheets" not in panel_prompt(shot(1), [])
    assert "reference sheets" not in panel_prompt(shot(1, "mira"), [MIRA])  # no sheet drawn yet


@pytest.mark.parametrize("style", list(PanelStyle))
def test_reference_sheets_use_the_project_style_and_only_the_description(style: PanelStyle) -> None:
    prompt = reference_prompt(MIRA, style)
    assert MIRA.canonical_description in prompt
    assert f"Style: {STYLES[style]}" in prompt
    assert "Never photorealistic" in prompt
    assert "no clothing, accessories or props it does not mention" in prompt
    assert "An animal wears nothing unless the description says so" in prompt
    assert "outfit" not in prompt  # "identical outfit" put a sweater on a fox
    assert "neutral standing pose" in prompt


def test_paper_cutout_style_reaches_panels_and_reference_sheets() -> None:
    assert "pencil storyboard sketch" in panel_prompt(shot(1), [])
    cutout = panel_prompt(shot(1), [], PanelStyle.PAPER_CUTOUT)
    assert "paper cutout" in cutout
    assert "pencil" not in cutout
    assert "paper cutout" in reference_prompt(MIRA, PanelStyle.PAPER_CUTOUT)
    assert "pencil" not in reference_prompt(MIRA, PanelStyle.PAPER_CUTOUT)


def test_concept_phrase_is_a_short_visual_noun_phrase() -> None:
    from frameteller.application.prompts import concept_phrase
    from frameteller.domain import Character

    girl = Character("mira", "Mira", "young girl about 8 years old, small slim build, round face")
    assert concept_phrase(girl) == "young girl about 8 years old"
    cat = Character("cat", "Grey Cat", "tiny small kitten with short soft grey fur and white paws and amber eyes")
    assert concept_phrase(cat) == "tiny small kitten with short soft grey fur"
    assert concept_phrase(Character("x", "Owl", "   ,   ")) == "Owl"


def test_clean_plate_prompt_removes_only_the_object() -> None:
    from frameteller.application.prompts import clean_plate_prompt

    prompt = clean_plate_prompt("small grey kitten ")
    assert prompt.startswith("Remove the small grey kitten from the picture.")
    assert "Keep everything else identical" in prompt
    with pytest.raises(ValueError, match="object to remove"):
        clean_plate_prompt(" ")
