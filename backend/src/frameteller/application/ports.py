"""Ports: the interfaces use cases depend on. Adapters in infrastructure/ implement them."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from frameteller.domain import Animatic, Box, Character, Framing, MaskBitmap, MediaRef, Point, Project, TranscriptTurn

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


@dataclass(frozen=True, slots=True)
class ImageRequest:
    prompt: str
    size: str
    quality: str  # "low" for drafts, "high" for finals (maps to reasoning_strength)
    references: tuple[bytes, ...] = ()


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    data: bytes
    content_type: str
    response_id: str


@dataclass(frozen=True, slots=True)
class Segment:
    box: Box
    bitmap: MaskBitmap
    label: str = ""


@dataclass(frozen=True, slots=True)
class Job:
    kind: str
    idempotency_key: str
    payload: dict[str, str] = field(default_factory=dict)


# ---- ports ----


class SpeechToTextPort(Protocol):
    async def transcribe(self, audio: bytes, keywords: Sequence[str]) -> list[TranscriptTurn]: ...


class DirectorPort(Protocol):
    async def direct_turn(self, turn: TranscriptTurn, project: Project) -> DirectedTurn: ...

    async def extract_characters(
        self, turns: Sequence[TranscriptTurn], known: Sequence[Character]
    ) -> list[Character]: ...


class ImageGenerationPort(Protocol):
    async def generate(self, request: ImageRequest) -> GeneratedImage: ...

    async def edit(self, previous_response_id: str, prompt: str, size: str, quality: str) -> GeneratedImage: ...


class SegmentationPort(Protocol):
    async def segment_concept(self, image: bytes, concept: str) -> list[Segment]: ...

    async def segment_point(self, image: bytes, point: Point) -> Segment | None: ...


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
    """Persistent spend counters behind the application's budget policy."""

    async def spent_by_project(self, project_id: str) -> float: ...

    async def spent_on_day(self, day: str) -> float: ...

    async def record(self, project_id: str, day: str, cost_usd: float, what: str) -> None: ...
