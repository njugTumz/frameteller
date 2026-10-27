import pytest

from frameteller.application.prompts import edit_prompt, panel_prompt, reference_prompt
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
    assert "reference sheets" in prompt


def test_panel_prompt_without_cast() -> None:
    assert "reference sheets" not in panel_prompt(shot(1), [])


def test_reference_prompt_names_the_character() -> None:
    assert MIRA.canonical_description in reference_prompt(MIRA)


def test_concept_phrase_is_a_short_visual_noun_phrase() -> None:
    from frameteller.application.prompts import concept_phrase
    from frameteller.domain import Character

    girl = Character("mira", "Mira", "young girl about 8 years old, small slim build, round face")
    assert concept_phrase(girl) == "young girl about 8 years old"
    cat = Character("cat", "Grey Cat", "tiny small kitten with short soft grey fur and white paws and amber eyes")
    assert concept_phrase(cat) == "tiny small kitten with short soft grey fur"
    assert concept_phrase(Character("x", "Owl", "   ,   ")) == "Owl"
