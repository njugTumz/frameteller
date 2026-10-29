"""Review records on panels, sheets and the supervisor log (ADR 0012)."""

import pytest

from frameteller.domain import (
    Decision,
    InvalidValueError,
    Issue,
    MediaRef,
    Outcome,
    PanelReview,
    Project,
    Severity,
    SheetReview,
    Size,
    SupervisorEntry,
    Verdict,
)
from frameteller.domain.review import SUPERVISOR_LOG_SIZE
from tests.builders import project
from tests.fakes import verdict

VEST = Issue("CONT-04", Severity.MAJOR, "a blue vest")


def drawn() -> Project:
    p = project()
    p.panel("s1").record_render(1, MediaRef("panels/s1/r1"), "resp_1", Size(1920, 1280))
    return p


def test_confidence_must_be_between_0_and_1() -> None:
    with pytest.raises(InvalidValueError):
        Verdict(Decision.PASS, 1.5, (), "", "", (), "m", 1, ())


def test_only_blockers_and_majors_are_serious_and_a_fix_needs_an_instruction() -> None:
    v = verdict(Decision.FIX, VEST, Issue("CONT-08", Severity.MINOR, "x"), fix="remove the vest", target="fox")
    assert v.serious_issues == (VEST,)
    assert v.can_fix
    assert not verdict(Decision.FIX, VEST).can_fix  # no instruction


def test_a_review_counts_only_for_the_render_it_checked() -> None:
    p = drawn()
    assert not p.record_panel_review("s1", PanelReview(2, Outcome.CHECKED, verdict()))
    assert p.record_panel_review("s1", PanelReview(1, Outcome.CHECKED, verdict()))
    p.panel("s1").record_render(2, MediaRef("panels/s1/r2"), "resp_2", Size(1920, 1280))
    assert p.panel("s1").review is None  # a new render clears the old badge


def test_accept_anyway_only_after_needs_your_eye() -> None:
    p = drawn()
    p.record_panel_review("s1", PanelReview(1, Outcome.CHECKED, verdict()))
    with pytest.raises(InvalidValueError):
        p.accept_panel("s1")
    p.record_panel_review("s1", PanelReview(1, Outcome.NEEDS_USER, verdict(Decision.ASK, VEST)))
    assert p.accept_panel("s1").outcome is Outcome.ACCEPTED


def test_a_sheet_review_counts_only_for_the_current_sheet() -> None:
    p = project()
    old = SheetReview(MediaRef("refs/old.webp"), Outcome.NEEDS_USER, verdict(), "x")
    assert not p.record_sheet_review("cat", old)
    current = SheetReview(MediaRef("refs/cat.webp"), Outcome.NEEDS_USER, verdict(), "x")
    assert p.record_sheet_review("cat", current)
    assert p.accept_sheet("cat").outcome is Outcome.ACCEPTED


def test_the_supervisor_log_keeps_the_latest_entries() -> None:
    p = project()
    for n in range(SUPERVISOR_LOG_SIZE + 5):
        p.log_supervisor(SupervisorEntry("2026-10-29T12:00:00", "Shot 1", Outcome.CHECKED, f"m{n}", (), "m"))
    assert len(p.supervisor_log) == SUPERVISOR_LOG_SIZE
    assert p.supervisor_log[-1].message == f"m{SUPERVISOR_LOG_SIZE + 4}"
