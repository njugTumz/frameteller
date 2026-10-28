"""Events a project emits while the user works: what the live session pushes to the client."""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.domain import Character, Shot, TranscriptTurn


@dataclass(frozen=True, slots=True)
class TranscriptUpdated:
    """Cumulative text of the turn in progress: replaces the previous one."""

    text: str


@dataclass(frozen=True, slots=True)
class TurnFinished:
    turn: TranscriptTurn


@dataclass(frozen=True, slots=True)
class ShotCreated:
    shot: Shot


@dataclass(frozen=True, slots=True)
class ShotUpdated:
    """A later turn revealed who or what an earlier shot showed. Its panel is outdated until redrawn."""

    shot: Shot


@dataclass(frozen=True, slots=True)
class ShotsReplaced:
    """A corrected turn was re-directed: `shots` (renumbered) took the place of `removed_shot_ids`."""

    turn: TranscriptTurn
    removed_shot_ids: tuple[str, ...]
    shots: tuple[Shot, ...]


@dataclass(frozen=True, slots=True)
class CastProposed:
    """New characters with freshly drawn reference sheets, waiting for approval (ADR 0004)."""

    characters: tuple[Character, ...]


@dataclass(frozen=True, slots=True)
class JobUpdated:
    kind: str
    key: str
    status: str  # queued | running | succeeded | failed
    shot_id: str | None = None
    revision: int | None = None
    message: str | None = None  # user-facing, on failure


@dataclass(frozen=True, slots=True)
class SessionFailed:
    """Something went wrong but the session carries on (or has ended, if `fatal`)."""

    message: str
    fatal: bool = False


@dataclass(frozen=True, slots=True)
class SessionEnded:
    turns: int
    shots: int


ProjectEvent = (
    TranscriptUpdated
    | TurnFinished
    | ShotCreated
    | ShotUpdated
    | ShotsReplaced
    | CastProposed
    | JobUpdated
    | SessionFailed
    | SessionEnded
)
