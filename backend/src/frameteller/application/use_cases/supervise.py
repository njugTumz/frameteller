"""The continuity supervisor (ADR 0012): review every new sheet and render, fix drafts it can, ask about the rest.

Policy, per panel revision:
- no blocker or major issue: done ("Checked", or "Fixed" after a fix);
- a fixable issue on a draft, with confidence: one appearance edit named by the reviewer, then a re-review;
  at most `max_fixes` edits per render, each within the project's budget;
- anything else (a final render, low confidence, an issue an edit cannot fix, the fixes ran out, the budget
  ran out): the user decides. Finals are never changed automatically, only reported.
Reviews run as background jobs and never block drawing. A review of a render that was replaced meanwhile is
dropped.
"""

from __future__ import annotations

from collections.abc import Sequence

from frameteller.application import costs
from frameteller.application.errors import BudgetExceededError
from frameteller.application.events import SupervisorFixed, SupervisorNeedsUser, SupervisorReviewed
from frameteller.application.jobs import edit_job
from frameteller.application.ports import (
    BudgetGuard,
    Clock,
    EventPublisher,
    JobQueuePort,
    ProjectRepository,
    Quality,
    ReferenceSheet,
    ReviewerPort,
    ReviewRequest,
    RubricLibrary,
)
from frameteller.application.rubrics import RubricSet
from frameteller.application.use_cases.edit_panel_appearance import EditPanelAppearance
from frameteller.application.use_cases.requests import JobTicket, RequestCastReferences
from frameteller.domain import (
    DomainError,
    InvalidValueError,
    Issue,
    Outcome,
    PanelReview,
    PanelStatus,
    Project,
    SheetReview,
    Shot,
    SupervisorEntry,
    Verdict,
)

PANEL_RUBRICS = ("panel-continuity", "shot")
FIX_RUBRIC = "edit"
SHEET_RUBRIC = "cast"
MAX_FIXES = 2
MIN_CONFIDENCE = 0.6


def _rules(issues: Sequence[Issue]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(i.rule_id for i in issues))


def _describe(issues: Sequence[Issue]) -> str:
    return "; ".join(i.description.strip().rstrip(".") for i in issues)


def _tries(n: int) -> str:
    return f"{n} {'try' if n == 1 else 'tries'}"


class SupervisePanel:
    """Background job after every draft and final render."""

    def __init__(
        self,
        repo: ProjectRepository,
        reviewer: ReviewerPort,
        rubrics: RubricLibrary,
        edit: EditPanelAppearance,
        budget: BudgetGuard,
        events: EventPublisher,
        clock: Clock,
        *,
        max_fixes: int = MAX_FIXES,
        min_confidence: float = MIN_CONFIDENCE,
    ) -> None:
        self._repo, self._reviewer, self._rubrics, self._edit = repo, reviewer, rubrics, edit
        self._budget, self._events, self._clock = budget, events, clock
        self._max_fixes, self._min_confidence = max_fixes, min_confidence

    async def execute(self, project_id: str, shot_id: str, revision: int, quality: Quality) -> PanelReview | None:
        fixed: list[Verdict] = []  # the verdicts whose fixes were applied, in order
        while True:
            project = await self._repo.get(project_id)
            panel = project.panel(shot_id)
            if not project.continuity_checks or panel.revision != revision or panel.status is not PanelStatus.READY:
                return None  # checks are off, or the user drew a new render meanwhile
            shot = project.shot(shot_id)
            names = (*PANEL_RUBRICS, FIX_RUBRIC) if fixed else PANEL_RUBRICS
            last = fixed[-1] if fixed else None
            try:
                await self._budget.charge(project_id, costs.REVIEW, f"review {shot_id} r{revision}")
            except BudgetExceededError:
                return None  # no review is better than no drawing: the budget is for panels first
            assert panel.image is not None  # a ready panel has an image
            verdict = await self._reviewer.review(
                ReviewRequest(
                    images=(panel.image,),
                    rubric=RubricSet(tuple(self._rubrics.get(n) for n in names)),
                    style=project.style,
                    reference_sheets=_sheets(project, shot),
                    shot=shot,
                    subject=f"Requested edit: {last.fix_instruction} (on the {last.fix_target})" if last else "",
                    previous_issues=last.serious_issues if last else (),
                )
            )
            serious = verdict.serious_issues
            if not serious:
                return await self._passed(project_id, shot, revision, verdict, fixed)
            reason = self._why_not_fix(verdict, quality, len(fixed))
            if reason:
                return await self._ask(project_id, shot, revision, verdict, len(fixed), reason)
            try:
                edited = await self._edit.execute(
                    project_id, shot_id, verdict.fix_target, verdict.fix_parts, verdict.fix_instruction, quality="low"
                )
            except BudgetExceededError:
                return await self._ask(project_id, shot, revision, verdict, len(fixed), "no budget left to fix it")
            except DomainError:
                return None  # the panel changed under us (a new render, a reveal): its own review will follow
            fixed, revision = [*fixed, verdict], edited.revision

    def _why_not_fix(self, verdict: Verdict, quality: Quality, fixes: int) -> str:
        if quality == "high":
            return "final render: reported, not changed"
        if not verdict.can_fix:
            return "an edit cannot fix this"
        if verdict.confidence < self._min_confidence:
            return "the reviewer was not sure"
        if fixes >= self._max_fixes:
            return f"still not right after {_tries(fixes)}"
        return ""

    async def _passed(
        self, project_id: str, shot: Shot, revision: int, verdict: Verdict, fixed: Sequence[Verdict]
    ) -> PanelReview | None:
        if fixed:
            first = fixed[0]
            done = "; ".join(dict.fromkeys(v.fix_instruction.strip().rstrip(".") for v in fixed))
            summary = f"Fixed: {done}"
            message = (
                f"Shot {shot.number}: {done} ({', '.join(_rules(first.serious_issues))}, "
                f"{_describe(first.serious_issues[:1])}). Fixed in {_tries(len(fixed))}."
            )
            outcome, rules = Outcome.FIXED, _rules(first.serious_issues)
        else:
            minor = len(verdict.issues)
            summary = "Checked" if not minor else f"Checked ({minor} minor note{'s' if minor > 1 else ''})"
            message = f"Shot {shot.number}: checked, no continuity issues" + (
                f" ({minor} minor: {_describe(verdict.issues)})." if minor else "."
            )
            outcome, rules = Outcome.CHECKED, _rules(verdict.issues)
        review = PanelReview(revision, outcome, verdict, len(fixed), summary)
        entry = self._entry(shot, outcome, message, rules, verdict.model)
        if not await self._record(project_id, shot.id, review, entry):
            return None
        event = SupervisorFixed(entry, revision, len(fixed)) if fixed else SupervisorReviewed(entry, revision)
        await self._events.publish(project_id, event)
        return review

    async def _ask(
        self, project_id: str, shot: Shot, revision: int, verdict: Verdict, fixes: int, reason: str
    ) -> PanelReview | None:
        serious = verdict.serious_issues
        summary = f"Needs your eye: {_describe(serious[:1])}"
        message = f"Shot {shot.number} needs your eye: {_describe(serious)} ({', '.join(_rules(serious))}; {reason})."
        review = PanelReview(revision, Outcome.NEEDS_USER, verdict, fixes, summary)
        entry = self._entry(shot, Outcome.NEEDS_USER, message, _rules(serious), verdict.model)
        if not await self._record(project_id, shot.id, review, entry):
            return None
        fix = verdict.fix_instruction if verdict.can_fix else ""
        await self._events.publish(project_id, SupervisorNeedsUser(entry, serious, fix, revision))
        return review

    def _entry(self, shot: Shot, outcome: Outcome, message: str, rules: tuple[str, ...], model: str) -> SupervisorEntry:
        at = self._clock.now().isoformat(timespec="seconds")
        return SupervisorEntry(at, f"Shot {shot.number}", outcome, message, rules, model, shot_id=shot.id)

    async def _record(self, project_id: str, shot_id: str, review: PanelReview, entry: SupervisorEntry) -> bool:
        def apply(project: Project) -> bool:
            kept = project.record_panel_review(shot_id, review)
            if kept:
                project.log_supervisor(entry)
            return kept

        return await self._repo.update(project_id, apply)


def _sheets(project: Project, shot: Shot) -> tuple[ReferenceSheet, ...]:
    cast = (project.bible.get(cid) for cid in shot.character_ids if cid in project.bible)
    return tuple(ReferenceSheet(c.name, c.canonical_description, c.reference) for c in cast if c.reference)


class ReviewSheet:
    """Background job after a reference sheet is drawn, before the cast is approved. Never fixes by itself:
    the user approves the cast anyway, so the issues show on the sheet with an "Apply fix" button."""

    def __init__(
        self,
        repo: ProjectRepository,
        reviewer: ReviewerPort,
        rubrics: RubricLibrary,
        budget: BudgetGuard,
        events: EventPublisher,
        clock: Clock,
    ) -> None:
        self._repo, self._reviewer, self._rubrics = repo, reviewer, rubrics
        self._budget, self._events, self._clock = budget, events, clock

    async def execute(self, project_id: str, character_id: str, reference_key: str) -> SheetReview | None:
        project = await self._repo.get(project_id)
        if not project.continuity_checks or character_id not in project.bible:
            return None
        character = project.bible.get(character_id)
        if character.reference is None or character.reference.key != reference_key:
            return None  # redrawn meanwhile: the new sheet has its own review
        try:
            await self._budget.charge(project_id, costs.REVIEW, f"review sheet {character_id}")
        except BudgetExceededError:
            return None
        verdict = await self._reviewer.review(
            ReviewRequest(
                images=(character.reference,),
                rubric=RubricSet((self._rubrics.get(SHEET_RUBRIC),)),
                style=project.style,
                subject=f"{character.name}: {character.canonical_description}",
            )
        )
        serious = verdict.serious_issues
        subject = f"{character.name}'s reference sheet"
        if serious:
            outcome = Outcome.NEEDS_USER
            summary = _describe(serious)
            message = f"{subject} needs your eye before you approve: {summary} ({', '.join(_rules(serious))})."
        else:
            outcome, summary = Outcome.CHECKED, "Checked"
            message = f"{subject}: checked, it matches the description."
        review = SheetReview(character.reference, outcome, verdict, summary)
        at = self._clock.now().isoformat(timespec="seconds")
        entry = SupervisorEntry(
            at, subject, outcome, message, _rules(serious or verdict.issues), verdict.model, character_id=character_id
        )

        def apply(p: Project) -> bool:
            kept = p.record_sheet_review(character_id, review)
            if kept:
                p.log_supervisor(entry)
            return kept

        if not await self._repo.update(project_id, apply):
            return None
        fix = verdict.fix_instruction if serious else ""
        event = SupervisorNeedsUser(entry, serious, fix) if serious else SupervisorReviewed(entry)
        await self._events.publish(project_id, event)
        return review


class ApplySuggestedFix:
    """The user's "Apply suggested fix": a panel gets the reviewer's appearance edit, a sheet is redrawn with the
    reviewer's correction. Both go through the usual request paths (allowances, idempotency, job updates)."""

    def __init__(self, repo: ProjectRepository, jobs: JobQueuePort, cast: RequestCastReferences) -> None:
        self._repo, self._jobs, self._cast = repo, jobs, cast

    async def for_panel(self, project_id: str, shot_id: str) -> JobTicket:
        project = await self._repo.get(project_id)
        panel = project.panel(shot_id)
        review = panel.review
        if review is None or not review.verdict.fix_instruction.strip() or review.revision != panel.revision:
            raise InvalidValueError(f"shot {shot_id}: no suggested fix for the current render")
        v = review.verdict
        instruction = f"{v.fix_instruction.strip().rstrip('.')} (on the {v.fix_target.strip()})"
        job = edit_job(project_id, shot_id, panel.current_revision, instruction)
        return JobTicket.of(job, await self._jobs.enqueue(job))

    async def for_sheet(self, project_id: str, character_id: str) -> JobTicket:
        project = await self._repo.get(project_id)
        review = project.sheet_reviews.get(character_id)
        character = project.bible.get(character_id)
        if review is None or review.reference != character.reference or review.outcome is not Outcome.NEEDS_USER:
            raise InvalidValueError(f"{character_id}: no suggested fix for the current sheet")
        v = review.verdict
        correction = v.fix_instruction.strip() or "; ".join(
            f"{i.description.strip().rstrip('.')}: correct it" for i in v.serious_issues
        )
        return await self._cast.execute(project_id, [character_id], correction=correction)


class AcceptReview:
    """The user's "Accept anyway": keep the panel or sheet as it is; the badge says so."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def for_panel(self, project_id: str, shot_id: str) -> PanelReview:
        return await self._repo.update(project_id, lambda p: p.accept_panel(shot_id))

    async def for_sheet(self, project_id: str, character_id: str) -> SheetReview:
        return await self._repo.update(project_id, lambda p: p.accept_sheet(character_id))


class SetContinuityChecks:
    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(self, project_id: str, enabled: bool) -> bool:
        def apply(p: Project) -> bool:
            p.continuity_checks = enabled
            return enabled

        return await self._repo.update(project_id, apply)
