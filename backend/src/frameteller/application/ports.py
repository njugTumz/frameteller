"""Ports: the interfaces use cases depend on. Adapters in infrastructure/ implement them."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

from frameteller.application.events import ProjectEvent
from frameteller.application.rubrics import Rubric, RubricSet
from frameteller.domain import (
    Animatic,
    Box,
    Character,
    Framing,
    Issue,
    MaskBitmap,
    MediaRef,
    PanelStyle,
    Point,
    Project,
    Shot,
    Size,
    TranscriptTurn,
    Verdict,
)

# ---- data crossing the ports ----


@dataclass(frozen=True, slots=True)
class ShotDraft:
    """A shot as proposed by the director, before the project numbers it."""

    framing: Framing
    character_ids: tuple[str, ...]
    setting: str
    action: str
    dialogue: str
    source_turn_ids: tuple[str, ...]
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ShotRevision:
    """A reveal: a later turn says who or what an earlier, vaguely described shot showed."""

    shot_id: str
    character_ids: tuple[str, ...]
    action: str


@dataclass(frozen=True, slots=True)
class DirectedTurn:
    new_characters: tuple[Character, ...]
    shots: tuple[ShotDraft, ...]
    revisions: tuple[ShotRevision, ...] = ()
    # One friendly sentence when the narration named a real person or a copyrighted character: no character or
    # shot was made for them, and the narrator is asked for an original one instead.
    refusal: str = ""


@dataclass(frozen=True, slots=True)
class EditIntent:
    """A spoken edit routed by the director: what to change, on which object, naming every part (ADR 0005)."""

    target: str
    parts: tuple[str, ...]
    change: str


Quality = Literal["low", "high"]  # drafts vs finals (maps to reasoning_strength)
Aspect = Literal["square", "panel"]  # the adapter maps these to sizes from settings


@dataclass(frozen=True, slots=True)
class ImageRequest:
    prompt: str
    quality: Quality
    aspect: Aspect
    references: tuple[MediaRef, ...] = ()


@dataclass(frozen=True, slots=True)
class EditRequest:
    """An edit of an image we stored: it goes back to the model with the reference sheets, never chained by
    response id, because Muse Image may forget a response within minutes (ADR 0014)."""

    image: MediaRef
    prompt: str
    quality: Quality
    references: tuple[MediaRef, ...] = ()


@dataclass(frozen=True, slots=True)
class StoredImage:
    """An image the adapter already persisted. Model output is never kept anywhere else."""

    ref: MediaRef
    response_id: str
    size: Size


@dataclass(frozen=True, slots=True)
class Segment:
    box: Box
    bitmap: MaskBitmap
    label: str = ""
    cutout: MediaRef | None = None  # RGBA cut-out of the object, stored by the adapter


@dataclass(frozen=True, slots=True)
class CutoutLayer:
    """A cut-out pasted on a clean plate: its top-left at (left, top) in panel pixels, scaled from that corner."""

    image: bytes
    left: int
    top: int
    scale: float


@dataclass(frozen=True, slots=True)
class Job:
    kind: str
    idempotency_key: str
    payload: dict[str, str] = field(default_factory=dict)


class SpeechMode(StrEnum):
    NARRATION = "narration"  # one narrator, low-latency turn endpointing
    CO_DIRECTION = "co_direction"  # speaker labels, chosen before recording starts


@dataclass(frozen=True, slots=True)
class SpeechOptions:
    mode: SpeechMode = SpeechMode.NARRATION
    keywords: tuple[str, ...] = ()
    language_bias: str | None = None


@dataclass(frozen=True, slots=True)
class PartialTranscript:
    """Cumulative text of the turn in progress: replaces the previous partial."""

    text: str


@dataclass(frozen=True, slots=True)
class TurnStarted:
    turn_id: str
    start_ms: int


@dataclass(frozen=True, slots=True)
class TurnEnded:
    turn_id: str
    end_ms: int


@dataclass(frozen=True, slots=True)
class SpeakerIdentified:
    turn_id: str
    speaker: str


@dataclass(frozen=True, slots=True)
class TurnCompleted:
    turn: TranscriptTurn


@dataclass(frozen=True, slots=True)
class AudioProgress:
    """How much audio the transcriber has processed. Partials up to about this point have arrived."""

    processed_ms: int


SpeechEvent = PartialTranscript | TurnStarted | TurnEnded | SpeakerIdentified | TurnCompleted | AudioProgress


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """One model call, for observability and cost reporting."""

    model: str
    operation: str
    latency_ms: int
    cost_usd: float
    project_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    ok: bool = True


# ---- ports ----


class SpeechToTextPort(Protocol):
    def stream(self, audio: AsyncIterator[bytes], options: SpeechOptions) -> AsyncIterator[SpeechEvent]:
        """Live transcription of raw PCM chunks, yielding typed events until the stream ends."""
        ...

    async def transcribe_file(self, wav: bytes, options: SpeechOptions) -> list[TranscriptTurn]: ...


class DirectorPort(Protocol):
    async def direct_turn(self, turn: TranscriptTurn, project: Project) -> DirectedTurn: ...

    async def direct_story(self, project: Project) -> DirectedTurn:
        """Full-story pass over every turn, only on demand (ADR 0002)."""
        ...

    async def extract_characters(
        self, turns: Sequence[TranscriptTurn], known: Sequence[Character]
    ) -> list[Character]: ...

    async def interpret_edit(self, instruction: str, shot: Shot, cast: Sequence[Character]) -> EditIntent:
        """Turn "her coat is red now" into a target, its parts and the change."""
        ...


class ImageGenerationPort(Protocol):
    async def generate(self, request: ImageRequest, store_as: str) -> StoredImage: ...

    async def edit(self, request: EditRequest, store_as: str) -> StoredImage: ...


@dataclass(frozen=True, slots=True)
class ReferenceSheet:
    """A character's approved look, as the reviewer compares a panel against it."""

    name: str
    description: str
    image: MediaRef


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    """One review: the image(s) under review, what they must match, and the rules to check (ADR 0012)."""

    images: tuple[MediaRef, ...]  # the panel or the sheet under review
    rubric: RubricSet
    style: PanelStyle
    reference_sheets: tuple[ReferenceSheet, ...] = ()
    shot: Shot | None = None
    subject: str = ""  # a sheet's character and description, or the edit that was asked for
    previous_issues: tuple[Issue, ...] = ()  # what a fix tried to repair, for the re-review


class ReviewerPort(Protocol):
    async def review(self, request: ReviewRequest) -> Verdict:
        """Check the request against its rubric. The verdict names the model that served it."""
        ...


class RubricLibrary(Protocol):
    def get(self, rubric_id: str) -> Rubric:
        """The current text of a rubric (agents/<id>.md), parsed. Raises RubricError if it is missing or bad."""
        ...


class SegmentationPort(Protocol):
    async def segment_concept(self, image: MediaRef, concept: str, store_prefix: str) -> list[Segment]: ...

    async def segment_point(self, image: MediaRef, point: Point, store_prefix: str) -> Segment | None:
        """`point` is in media pixels; convert preview clicks with Point.to_media first."""
        ...


class MediaStoragePort(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> MediaRef: ...

    async def get(self, ref: MediaRef) -> bytes: ...

    async def delete(self, ref: MediaRef) -> None:
        """Remove a stored file. Deleting one that is already gone is not an error."""
        ...


class ProjectRepository(Protocol):
    async def get(self, project_id: str) -> Project: ...

    async def save(self, project: Project) -> None: ...

    async def update[T](self, project_id: str, change: Callable[[Project], T]) -> T:
        """Load, apply `change` and save as one step, so concurrent use cases never overwrite each other.

        Slow work (model calls) happens before update(); `change` must be quick and must not await.
        """
        ...


class JobQueuePort(Protocol):
    async def enqueue(self, job: Job) -> bool:
        """Queue a job. Returns False if a job with the same idempotency key was already queued."""
        ...


Progress = Callable[[float], Awaitable[None]]


class VideoRendererPort(Protocol):
    async def render(
        self,
        animatic: Animatic,
        frames: Mapping[str, bytes],
        recordings: Mapping[str, bytes],
        *,
        subtitles: bool,
        on_progress: Progress | None = None,
    ) -> bytes:
        """The MP4 animatic. `frames` by shot id, `recordings` by media key; progress is 0-1 of the timeline."""
        ...


@dataclass(frozen=True, slots=True)
class SheetRow:
    """One shot on the storyboard sheet. `image` is None when its panel is not drawn yet."""

    number: int
    framing: str
    action: str
    dialogue: str
    duration_ms: int
    image: bytes | None


class StoryboardSheetPort(Protocol):
    async def render(self, title: str, rows: Sequence[SheetRow]) -> bytes:
        """A printable PDF: the panels in a grid, each with its shot number, framing, action, dialogue and time."""
        ...


class VisitorQuota(Protocol):
    """How many times a visitor did something limited today (start a project). `visitor` is already a hash."""

    async def used(self, visitor: str, day: str, kind: str) -> int: ...

    async def add(self, visitor: str, day: str, kind: str) -> None: ...


class ShareIndex(Protocol):
    """Which project a share token opens. Kept apart so a share link never reveals the project id."""

    async def put(self, token: str, project_id: str) -> None: ...

    async def find(self, token: str) -> str | None: ...

    async def delete(self, token: str) -> None: ...


class SharePreviewPort(Protocol):
    async def contact_sheet(self, title: str, panels: Sequence[bytes]) -> bytes:
        """A 1200x630 PNG for link previews (og:image): the title and up to six panels."""
        ...


class CompositorPort(Protocol):
    async def compose(self, background: bytes, layers: Sequence[CutoutLayer], size: Size) -> bytes:
        """Paste the layers in order on the background, resized to `size`. Returns a WebP image."""
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new_id(self) -> str: ...


class EventPublisher(Protocol):
    async def publish(self, project_id: str, event: ProjectEvent) -> None:
        """Push an event to whoever follows the project (the live session). Must never raise."""
        ...


class BudgetGuard(Protocol):
    async def charge(self, project_id: str, cost_usd: float, what: str) -> None:
        """Record spend, or raise BudgetExceededError before any money is spent."""
        ...


class SpendLedger(Protocol):
    """Persistent spend counters behind the budget policy, plus per-call usage records."""

    async def spent_by_project(self, project_id: str) -> float: ...

    async def spent_on_day(self, day: str) -> float: ...

    async def record(self, project_id: str, day: str, cost_usd: float, what: str) -> None: ...

    async def record_usage(self, usage: UsageRecord) -> None:
        """Observability only: budget totals come from record(), so usage is never counted twice."""
        ...
