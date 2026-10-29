"""Events a project emits while the user works: what the live session pushes to the client."""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.domain import Character, Issue, MediaRef, Script, Shot, SupervisorEntry, TranscriptTurn


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
    progress: float | None = None  # 0-1, for long jobs (the animatic export) while running


@dataclass(frozen=True, slots=True)
class SessionFailed:
    """Something went wrong but the session carries on (or has ended, if `fatal`)."""

    message: str
    fatal: bool = False


@dataclass(frozen=True, slots=True)
class NoSpeechHeard:
    """Seconds of near-silent audio and no words yet: the microphone is probably muted or the wrong one."""

    after_ms: int
    level: float  # the loudest 80 ms so far, as RMS from 0 to 1


@dataclass(frozen=True, slots=True)
class SessionEnded:
    turns: int
    shots: int
    heard: bool = True  # False when no words were heard at all


@dataclass(frozen=True, slots=True)
class SupervisorReviewed:
    """The continuity supervisor checked a panel or a sheet and found nothing to fix (ADR 0012)."""

    entry: SupervisorEntry
    revision: int | None = None  # the panel revision reviewed; None for a sheet


@dataclass(frozen=True, slots=True)
class SupervisorFixed:
    """It fixed a draft panel by itself, in `fixes` appearance edits, and the fixed panel passed."""

    entry: SupervisorEntry
    revision: int
    fixes: int


@dataclass(frozen=True, slots=True)
class SupervisorNeedsUser:
    """It found issues it will not or could not fix: the user decides (apply the fix, accept or redraw)."""

    entry: SupervisorEntry
    issues: tuple[Issue, ...]
    fix_instruction: str
    revision: int | None = None


@dataclass(frozen=True, slots=True)
class ScriptAccepted:
    """A script was parsed for a teleprompter or "Read it to me" session: the paragraphs, as the server split them."""

    script: Script


@dataclass(frozen=True, slots=True)
class TeleprompterAdvanced:
    """The reader finished a paragraph (or pressed Space): `paragraph` is now current, counted through the script."""

    paragraph: int


@dataclass(frozen=True, slots=True)
class ParagraphVoiced:
    """ "Read it to me": a paragraph's narration is synthesized and stored, ready to play."""

    paragraph: int
    episode: int
    text: str  # what the voice says (translated if the language is not the script's)
    original: str
    audio: MediaRef
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ReadingPaused:
    """ "Read it to me" stopped before `next_paragraph`: the listener paused, or an episode's drafts are drawing."""

    next_paragraph: int
    next_episode: int
    reason: str  # "user" | "episode"


@dataclass(frozen=True, slots=True)
class ReadingResumed:
    next_paragraph: int


ProjectEvent = (
    TranscriptUpdated
    | TurnFinished
    | ShotCreated
    | ShotUpdated
    | ShotsReplaced
    | CastProposed
    | JobUpdated
    | SessionFailed
    | NoSpeechHeard
    | SessionEnded
    | SupervisorReviewed
    | SupervisorFixed
    | SupervisorNeedsUser
    | ScriptAccepted
    | TeleprompterAdvanced
    | ParagraphVoiced
    | ReadingPaused
    | ReadingResumed
)
