"""Rubrics as code (ADR 0012): the parser, and the four real rubric files in agents/."""

from pathlib import Path

import pytest

from frameteller.application.rubrics import RubricError, RubricSet, parse_rubric
from frameteller.domain import Severity
from frameteller.infrastructure.review import FileRubricLibrary
from tests.fakes import rubric_text

AGENTS = Path(__file__).resolve().parents[3] / "agents"


def test_a_rubric_has_ids_severities_tests_and_a_hash_of_its_text() -> None:
    text = rubric_text("edit", ("EDIT-01", "blocker"), ("EDIT-02", "minor"))
    r = parse_rubric(text)
    assert (r.id, r.version) == ("edit", 1)
    assert [(x.id, x.severity) for x in r.rules] == [("EDIT-01", Severity.BLOCKER), ("EDIT-02", Severity.MINOR)]
    assert r.rule("EDIT-02").test == "test EDIT-02"  # type: ignore[union-attr]
    assert len(r.hash) == 12
    assert parse_rubric(text.replace("Guidance.", "Other guidance.")).hash != r.hash


@pytest.mark.parametrize(
    "text",
    [
        "# no front matter\n| CONT-01 | blocker | x |\n",
        rubric_text("edit"),  # no rules
        rubric_text("edit", ("EDIT-01", "blocker"), ("EDIT-01", "major")),  # duplicate id
    ],
)
def test_malformed_rubrics_are_refused(text: str) -> None:
    with pytest.raises(RubricError):
        parse_rubric(text)


def test_the_four_pipeline_rubrics_load_with_stable_unique_ids() -> None:
    library = FileRubricLibrary(AGENTS)
    rubrics = RubricSet(tuple(library.get(n) for n in ("cast", "panel-continuity", "shot", "edit")))
    ids = [r.id for r in rubrics.rules]
    assert len(ids) == len(set(ids))
    assert {"CAST-04", "CONT-01", "CONT-04", "SHOT-01", "EDIT-02"} <= set(ids)
    assert rubrics.rule("CONT-01").severity is Severity.BLOCKER  # type: ignore[union-attr]
    assert set(rubrics.hashes) == {"cast", "panel-continuity", "shot", "edit"}


def test_the_library_refuses_unknown_or_unsafe_names(tmp_path: Path) -> None:
    (tmp_path / "shot.md").write_text(rubric_text("edit", ("EDIT-01", "major")))
    library = FileRubricLibrary(tmp_path)
    with pytest.raises(RubricError):
        library.get("../secrets")
    with pytest.raises(RubricError):
        library.get("cast")  # missing
    with pytest.raises(RubricError):
        library.get("shot")  # the file declares another id


def test_panel_continuity_checks_the_outfit_worn_in_the_shot() -> None:
    rubric = parse_rubric((AGENTS / "panel-continuity.md").read_text())
    assert rubric.version == 2
    [outfit] = (r for r in rubric.rules if r.id == "CONT-09")
    assert "not their everyday clothes" in outfit.test
    assert "never\nagainst what they wore earlier" in rubric.guidance
