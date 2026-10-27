"""In-memory fakes for every application port. No network, no disk."""

from __future__ import annotations

import copy
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

from frameteller.application.ports import (
    DirectedTurn,
    GeneratedImage,
    ImageRequest,
    Job,
    Segment,
)
from frameteller.domain import Animatic, Character, MediaRef, Point, Project, TranscriptTurn


class InMemoryProjectRepository:
    """Stores deep copies, so a use case that forgets to save() loses its changes, as it would in Blob Storage."""

    def __init__(self, *projects: Project) -> None:
        self._data: dict[str, Project] = {p.id: copy.deepcopy(p) for p in projects}
        self.saves = 0

    async def get(self, project_id: str) -> Project:
        return copy.deepcopy(self._data[project_id])

    async def save(self, project: Project) -> None:
        self._data[project.id] = copy.deepcopy(project)
        self.saves += 1

    def peek(self, project_id: str) -> Project:
        return copy.deepcopy(self._data[project_id])


class FakeDirector:
    def __init__(self, turns: dict[str, DirectedTurn] | None = None, characters: Sequence[Character] = ()) -> None:
        self.turns = turns or {}
        self.characters = list(characters)
        self.calls: list[str] = []

    async def direct_turn(self, turn: TranscriptTurn, project: Project) -> DirectedTurn:
        self.calls.append(turn.id)
        return self.turns[turn.id]

    async def extract_characters(self, turns: Sequence[TranscriptTurn], known: Sequence[Character]) -> list[Character]:
        self.calls.append("extract_characters")
        return list(self.characters)


class FakeImageGeneration:
    def __init__(self) -> None:
        self.generated: list[ImageRequest] = []
        self.edits: list[tuple[str, str]] = []
        self.fail_next = False

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("model unavailable")
        self.generated.append(request)
        n = len(self.generated) + len(self.edits)
        return GeneratedImage(f"image-{n}".encode(), "image/webp", f"resp_{n}")

    async def edit(self, previous_response_id: str, prompt: str, size: str, quality: str) -> GeneratedImage:
        self.edits.append((previous_response_id, prompt))
        n = len(self.generated) + len(self.edits)
        return GeneratedImage(f"image-{n}".encode(), "image/webp", f"resp_{n}")

    @property
    def calls(self) -> int:
        return len(self.generated) + len(self.edits)


class FakeSegmentation:
    def __init__(self, by_concept: dict[str, Segment] | None = None, at_point: Segment | None = None) -> None:
        self.by_concept = by_concept or {}
        self.at_point = at_point
        self.concept_calls: list[str] = []
        self.point_calls: list[Point] = []

    async def segment_concept(self, image: bytes, concept: str) -> list[Segment]:
        self.concept_calls.append(concept)
        return [self.by_concept[concept]] if concept in self.by_concept else []

    async def segment_point(self, image: bytes, point: Point) -> Segment | None:
        self.point_calls.append(point)
        return self.at_point


class FakeSpeechToText:
    def __init__(self, turns: Sequence[TranscriptTurn]) -> None:
        self.turns = list(turns)

    async def transcribe(self, audio: bytes, keywords: Sequence[str]) -> list[TranscriptTurn]:
        return list(self.turns)


class InMemoryMediaStorage:
    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> MediaRef:
        self.files[key] = (data, content_type)
        return MediaRef(key)

    async def get(self, ref: MediaRef) -> bytes:
        return self.files[ref.key][0]


class InMemoryJobQueue:
    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self._keys: set[str] = set()

    async def enqueue(self, job: Job) -> bool:
        if job.idempotency_key in self._keys:
            return False
        self._keys.add(job.idempotency_key)
        self.jobs.append(job)
        return True


class FakeVideoRenderer:
    def __init__(self) -> None:
        self.rendered: list[tuple[Animatic, dict[str, bytes], bytes | None]] = []

    async def render(self, animatic: Animatic, frames: dict[str, bytes], narration: bytes | None) -> bytes:
        self.rendered.append((animatic, frames, narration))
        return b"mp4"


class FixedClock:
    def __init__(self, now: datetime | None = None) -> None:
        self.current = now or datetime(2026, 10, 28, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current


class SequentialIds:
    def __init__(self, prefix: str = "id") -> None:
        self.prefix, self.n = prefix, 0

    def new_id(self) -> str:
        self.n += 1
        return f"{self.prefix}{self.n}"


class InMemorySpendLedger:
    def __init__(self) -> None:
        self.by_project: dict[str, float] = defaultdict(float)
        self.by_day: dict[str, float] = defaultdict(float)
        self.entries: list[tuple[str, str, float, str]] = []

    async def spent_by_project(self, project_id: str) -> float:
        return self.by_project[project_id]

    async def spent_on_day(self, day: str) -> float:
        return self.by_day[day]

    async def record(self, project_id: str, day: str, cost_usd: float, what: str) -> None:
        self.by_project[project_id] += cost_usd
        self.by_day[day] += cost_usd
        self.entries.append((project_id, day, cost_usd, what))


class RecordingBudget:
    """BudgetGuard that never refuses and records every charge."""

    def __init__(self) -> None:
        self.charges: list[tuple[str, float, str]] = []

    async def charge(self, project_id: str, cost_usd: float, what: str) -> None:
        self.charges.append((project_id, cost_usd, what))

    @property
    def total(self) -> float:
        return sum(c for _, c, _ in self.charges)
