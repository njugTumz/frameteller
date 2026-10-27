"""Ports: the interfaces use cases depend on. Adapters in infrastructure/ implement them."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

from frameteller.domain import (
    Animatic,
    Box,
    Character,
    Framing,
    MaskBitmap,
    MediaRef,
    Point,
    Project,
    Size,
    TranscriptTurn,
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
class DirectedTurn:
    new_characters: tuple[Character, ...]
    shots: tuple[ShotDraft, ...]


Quality = Literal["low", "high"]  # drafts vs finals (maps to reasoning_strength)
Aspect = Literal["square", "panel"]  # the adapter maps these to sizes from settings


@dataclass(frozen=True, slots=True)
class ImageRequest:
    prompt: str
    quality: Quality
    aspect: Aspect
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


SpeechEvent = PartialTranscript | TurnStarted | TurnEnded | SpeakerIdentified | TurnCompleted


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


class ImageGenerationPort(Protocol):
    async def generate(self, request: ImageRequest, store_as: str) -> StoredImage: ...

    async def edit(self, previous_response_id: str, prompt: str, quality: Quality, store_as: str) -> StoredImage: ...


class SegmentationPort(Protocol):
    async def segment_concept(self, image: MediaRef, concept: str, store_prefix: str) -> list[Segment]: ...

    async def segment_point(self, image: MediaRef, point: Point, store_prefix: str) -> Segment | None:
        """`point` is in media pixels; convert preview clicks with Point.to_media first."""
        ...


class MediaStoragePort(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> MediaRef: ...

    async def get(self, ref: MediaRef) -> bytes: ...


class ProjectRepository(Protocol):
    async def get(self, project_id: str) -> Project: ...

    async def save(self, project: Project) -> None: ...


class JobQueuePort(Protocol):
    async def enqueue(self, job: Job) -> bool:
        """Queue a job. Returns False if a job with the same idempotency key was already queued."""
        ...


class VideoRendererPort(Protocol):
    async def render(self, animatic: Animatic, frames: dict[str, bytes], narration: bytes | None) -> bytes: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new_id(self) -> str: ...


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
