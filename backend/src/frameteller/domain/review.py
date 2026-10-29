"""The continuity supervisor's records: verdicts on panels and reference sheets, and its activity log (ADR 0012)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from frameteller.domain.errors import InvalidValueError
from frameteller.domain.media import MediaRef


class Severity(StrEnum):
    BLOCKER = "blocker"  # the panel tells the wrong story
    MAJOR = "major"  # a continuity break a viewer would notice
    MINOR = "minor"  # noted, never worth a redraw on its own


class Decision(StrEnum):
    """What the reviewer recommends."""

    PASS = "pass"
    FIX = "fix"  # an appearance edit can repair it
    ASK = "ask"  # an edit cannot, or the reviewer is unsure: the user decides


class Outcome(StrEnum):
    """What the supervisor did, shown as the panel's badge."""

    CHECKED = "checked"
    FIXED = "fixed"
    NEEDS_USER = "needs_user"
    ACCEPTED = "accepted"  # the user saw the issues and kept it


@dataclass(frozen=True, slots=True)
class Issue:
    rule_id: str
    severity: Severity
    description: str

    @property
    def serious(self) -> bool:
        return self.severity is not Severity.MINOR


@dataclass(frozen=True, slots=True)
class Verdict:
    decision: Decision
    confidence: float  # 0-1, the reviewer's own
    issues: tuple[Issue, ...]
    fix_instruction: str  # the appearance change, e.g. "remove the blue vest"; "" unless decision is fix
    fix_target: str  # the object to edit, e.g. "small orange fox"
    fix_parts: tuple[str, ...]  # every part the change must reach
    model: str  # the model that served this review
    latency_ms: int
    rubrics: tuple[tuple[str, str], ...]  # (rubric id, file hash) checked

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise InvalidValueError(f"confidence {self.confidence} is not between 0 and 1")

    @property
    def serious_issues(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.serious)

    @property
    def can_fix(self) -> bool:
        return self.decision is Decision.FIX and bool(self.fix_instruction.strip() and self.fix_target.strip())


@dataclass(frozen=True, slots=True)
class PanelReview:
    """The supervisor's last word on one base revision of a panel."""

    revision: int
    outcome: Outcome
    verdict: Verdict
    fixes: int = 0  # automatic fixes it took to get here
    summary: str = ""  # one plain sentence for the badge and the feed


@dataclass(frozen=True, slots=True)
class SheetReview:
    """The supervisor's word on one reference sheet, before the cast is approved."""

    reference: MediaRef  # the sheet that was checked; a new sheet needs a new review
    outcome: Outcome
    verdict: Verdict
    summary: str = ""


@dataclass(frozen=True, slots=True)
class SupervisorEntry:
    """One line of the studio's Supervisor feed."""

    at: str  # ISO 8601, UTC
    subject: str  # "Shot 4" or "Pip's reference sheet"
    outcome: Outcome
    message: str
    rule_ids: tuple[str, ...] = ()
    model: str = ""
    shot_id: str | None = None
    character_id: str | None = None


SUPERVISOR_LOG_SIZE = 100
