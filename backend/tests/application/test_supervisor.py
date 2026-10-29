"""The continuity supervisor's policy (ADR 0012): pass, fix, ask, the attempt cap, budget, finals, sheets."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from frameteller.application import costs
from frameteller.application.errors import BudgetExceededError
from frameteller.application.events import SupervisorFixed, SupervisorNeedsUser, SupervisorReviewed
from frameteller.application.jobs import EDIT_PANEL, GENERATE_CAST, REVIEW_SHEET
from frameteller.application.ports import Quality
from frameteller.application.use_cases import (
    AcceptReview,
    ApplySuggestedFix,
    EditPanelAppearance,
    GenerateCharacterReference,
    GeneratePanel,
    RequestCastReferences,
    ReviewSheet,
    SetContinuityChecks,
    SupervisePanel,
)
from frameteller.domain import Decision, InvalidValueError, Issue, Outcome, Severity, Verdict
from tests.application.conftest import World, make_world
from tests.builders import project
from tests.fakes import (
    FakeReviewer,
    FixedClock,
    InMemoryRubricLibrary,
    RecordingBudget,
    RecordingPublisher,
    SequentialIds,
    verdict,
)

VEST = Issue("CONT-02", Severity.MAJOR, "Mira wears a blue vest that is not on her reference sheet")
MINOR = Issue("CONT-03", Severity.MINOR, "Her scarf is a shade darker")
MISSING = Issue("CONT-01", Severity.BLOCKER, "The cat is missing")


def fix_vest(confidence: float = 0.9) -> Verdict:
    return verdict(
        Decision.FIX, VEST, confidence=confidence, fix="remove the blue vest", target="girl", parts=("vest",)
    )


class RefusingBudget(RecordingBudget):
    """Refuses every charge whose label starts with one of `refuse`."""

    def __init__(self, *refuse: str) -> None:
        super().__init__()
        self.refuse = refuse

    async def charge(self, project_id: str, cost_usd: float, what: str) -> None:
        if what.startswith(self.refuse):
            raise BudgetExceededError(what)
        await super().charge(project_id, cost_usd, what)


@dataclass
class Supervisor:
    world: World
    reviewer: FakeReviewer
    events: RecordingPublisher

    def panel(self) -> SupervisePanel:
        w = self.world
        edit = EditPanelAppearance(w.repo, w.images, w.budget, w.jobs)
        return SupervisePanel(w.repo, self.reviewer, InMemoryRubricLibrary(), edit, w.budget, self.events, FixedClock())

    def sheet(self) -> ReviewSheet:
        w = self.world
        return ReviewSheet(w.repo, self.reviewer, InMemoryRubricLibrary(), w.budget, self.events, FixedClock())


async def drawn(world: World, quality: Quality = "low") -> World:
    await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute(
        "p1",
        "s1",
        revision=1,
        quality=quality,
    )
    return world


def supervisor(world: World, *verdicts: Verdict) -> Supervisor:
    return Supervisor(world, FakeReviewer(*verdicts), RecordingPublisher())


async def test_a_clean_panel_is_checked_and_logged(world: World) -> None:
    s = supervisor(await drawn(world), verdict(Decision.PASS, MINOR))
    review = await s.panel().execute("p1", "s1", 1, "low")
    assert review is not None
    assert review.outcome is Outcome.CHECKED
    p = world.project()
    assert p.panel("s1").review == review
    [entry] = p.supervisor_log
    assert entry.message == "Shot 1: checked, no continuity issues (1 minor: Her scarf is a shade darker)."
    assert [type(e) for _, e in s.events.events] == [SupervisorReviewed]
    request = s.reviewer.requests[0]
    assert [r.id for r in request.rubric.rubrics] == ["panel-continuity", "shot"]
    assert [sheet.name for sheet in request.reference_sheets] == ["Mira"]
    assert ("p1", costs.REVIEW, "review s1 r1") in world.budget.charges


async def test_a_fixable_draft_is_edited_then_re_reviewed_and_marked_fixed(world: World) -> None:
    s = supervisor(await drawn(world), fix_vest(), verdict())
    review = await s.panel().execute("p1", "s1", 1, "low")
    assert review is not None
    assert review.outcome is Outcome.FIXED
    assert review.revision == 2
    assert review.fixes == 1
    assert "remove the blue vest" in world.images.edits[0][1]
    second = s.reviewer.requests[1]
    assert [r.id for r in second.rubric.rubrics] == ["panel-continuity", "shot", "edit"]
    assert second.subject == "Requested edit: remove the blue vest (on the girl)"
    assert second.previous_issues == (VEST,)
    [entry] = world.project().supervisor_log
    assert entry.message == (
        "Shot 1: remove the blue vest (CONT-02, Mira wears a blue vest that is not on her reference sheet). "
        "Fixed in 1 try."
    )
    assert entry.outcome is Outcome.FIXED
    assert entry.rule_ids == ("CONT-02",)
    [event] = s.events.of(SupervisorFixed)
    assert isinstance(event, SupervisorFixed)
    assert event.fixes == 1
    assert event.revision == 2


async def test_fixes_stop_after_two_tries_and_ask_the_user(world: World) -> None:
    s = supervisor(await drawn(world), fix_vest())  # the vest keeps coming back
    review = await s.panel().execute("p1", "s1", 1, "low")
    assert review is not None
    assert review.outcome is Outcome.NEEDS_USER
    assert len(world.images.edits) == 2
    assert review.revision == 3
    assert "still not right after 2 tries" in world.project().supervisor_log[-1].message
    [asked] = s.events.of(SupervisorNeedsUser)
    assert isinstance(asked, SupervisorNeedsUser)
    assert asked.fix_instruction == "remove the blue vest"


async def test_finals_are_never_changed_only_reported(world: World) -> None:
    s = supervisor(await drawn(world, "high"), fix_vest())
    review = await s.panel().execute("p1", "s1", 1, "high")
    assert review is not None
    assert review.outcome is Outcome.NEEDS_USER
    assert world.images.edits == []
    assert "final render: reported, not changed" in world.project().supervisor_log[-1].message


async def test_low_confidence_asks_instead_of_fixing(world: World) -> None:
    s = supervisor(await drawn(world), fix_vest(confidence=0.4))
    review = await s.panel().execute("p1", "s1", 1, "low")
    assert review is not None
    assert review.outcome is Outcome.NEEDS_USER
    assert world.images.edits == []
    assert "the reviewer was not sure" in world.project().supervisor_log[-1].message


async def test_an_issue_an_edit_cannot_fix_asks(world: World) -> None:
    s = supervisor(await drawn(world), verdict(Decision.ASK, MISSING))
    review = await s.panel().execute("p1", "s1", 1, "low")
    assert review is not None
    assert review.outcome is Outcome.NEEDS_USER
    assert world.images.edits == []
    assert world.project().supervisor_log[-1].message.startswith("Shot 1 needs your eye: The cat is missing")


async def test_no_budget_for_the_fix_asks_and_no_budget_for_a_review_skips_it() -> None:
    world = await drawn(make_world(project()))
    world.budget = RefusingBudget("edit")
    s = supervisor(world, fix_vest())
    review = await s.panel().execute("p1", "s1", 1, "low")
    assert review is not None
    assert review.outcome is Outcome.NEEDS_USER
    assert "no budget left to fix it" in world.project().supervisor_log[-1].message

    world.budget = RefusingBudget("review")
    assert await s.panel().execute("p1", "s1", 1, "low") is None


async def test_a_replaced_render_or_checks_off_is_not_reviewed(world: World) -> None:
    s = supervisor(await drawn(world))
    assert await s.panel().execute("p1", "s1", 7, "low") is None  # revision moved on
    await SetContinuityChecks(world.repo).execute("p1", False)
    assert await s.panel().execute("p1", "s1", 1, "low") is None
    assert s.reviewer.requests == []


async def test_accept_anyway_and_apply_suggested_fix_on_a_panel(world: World) -> None:
    s = supervisor(await drawn(world), fix_vest(confidence=0.3))
    await s.panel().execute("p1", "s1", 1, "low")
    request_cast = RequestCastReferences(world.repo, world.jobs, SequentialIds("n"))
    ticket = await ApplySuggestedFix(world.repo, world.jobs, request_cast).for_panel("p1", "s1")
    [job] = [j for j in world.jobs.jobs if j.kind == EDIT_PANEL]
    assert job.payload["instruction"] == "remove the blue vest (on the girl)"
    assert ticket.kind == EDIT_PANEL
    accepted = await AcceptReview(world.repo).for_panel("p1", "s1")
    assert accepted.outcome is Outcome.ACCEPTED


async def test_apply_suggested_fix_needs_a_suggestion(world: World) -> None:
    s = supervisor(await drawn(world), verdict(Decision.PASS))
    await s.panel().execute("p1", "s1", 1, "low")
    fix = ApplySuggestedFix(world.repo, world.jobs, RequestCastReferences(world.repo, world.jobs, SequentialIds("n")))
    with pytest.raises(InvalidValueError):
        await fix.for_panel("p1", "s1")
    with pytest.raises(InvalidValueError):
        await AcceptReview(world.repo).for_panel("p1", "s1")  # nothing to accept: it was checked


async def test_a_new_sheet_is_reviewed_and_issues_wait_for_the_user() -> None:
    world = make_world(project(approved=False))
    reviewer = FakeReviewer(verdict(Decision.ASK, Issue("CAST-02", Severity.MAJOR, "The cat wears a green sweater")))
    events = RecordingPublisher()
    cat = await GenerateCharacterReference(world.repo, world.images, world.budget, world.jobs).execute("p1", "cat")
    assert cat.reference is not None
    [job] = [j for j in world.jobs.jobs if j.kind == REVIEW_SHEET]
    s = Supervisor(world, reviewer, events)
    review = await s.sheet().execute("p1", "cat", job.payload["reference"])
    assert review is not None
    assert review.outcome is Outcome.NEEDS_USER
    assert world.project().sheet_reviews["cat"] == review
    assert world.images.edits == []  # sheets are never fixed by themselves
    assert [r.id for r in reviewer.requests[0].rubric.rubrics] == ["cast"]
    assert "needs your eye before you approve" in world.project().supervisor_log[-1].message

    fix = ApplySuggestedFix(world.repo, world.jobs, RequestCastReferences(world.repo, world.jobs, SequentialIds("n")))
    await fix.for_sheet("p1", "cat")
    [cast] = [j for j in world.jobs.jobs if j.kind == GENERATE_CAST]
    assert cast.payload["correction"] == "The cat wears a green sweater: correct it"
    assert (await AcceptReview(world.repo).for_sheet("p1", "cat")).outcome is Outcome.ACCEPTED


async def test_a_redrawn_sheet_drops_the_old_review() -> None:
    world = make_world(project(approved=False))
    await GenerateCharacterReference(world.repo, world.images, world.budget, world.jobs).execute("p1", "cat")
    s = supervisor(world)
    assert await s.sheet().execute("p1", "cat", "projects/p1/characters/cat/old") is None
    assert s.reviewer.requests == []
