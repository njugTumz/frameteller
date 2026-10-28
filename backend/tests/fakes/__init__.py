"""In-memory fakes for every application port. No network, no disk."""

from __future__ import annotations

import asyncio
import contextlib
import copy
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from frameteller.application.errors import ProjectNotFoundError
from frameteller.application.events import ProjectEvent
from frameteller.application.ports import (
    DirectedTurn,
    EditIntent,
    ImageRequest,
    Job,
    Quality,
    Segment,
    SpeechEvent,
    SpeechOptions,
    StoredImage,
    TurnCompleted,
    UsageRecord,
)
from frameteller.domain import Animatic, Character, MediaRef, Point, Project, Shot, Size, TranscriptTurn

PANEL_SIZE = Size(1920, 1280)


class InMemoryProjectRepository:
    """Stores deep copies, so a use case that forgets to save() loses its changes, as it would in Blob Storage."""

    def __init__(self, *projects: Project) -> None:
        self._data: dict[str, Project] = {p.id: copy.deepcopy(p) for p in projects}
        self.saves = 0
        self._lock = asyncio.Lock()

    async def get(self, project_id: str) -> Project:
        if project_id not in self._data:
            raise ProjectNotFoundError(project_id)
        return copy.deepcopy(self._data[project_id])

    async def save(self, project: Project) -> None:
        self._data[project.id] = copy.deepcopy(project)
        self.saves += 1

    async def update[T](self, project_id: str, change: Callable[[Project], T]) -> T:
        async with self._lock:
            project = await self.get(project_id)
            result = change(project)  # if change raises, nothing is saved
            await self.save(project)
            return result

    def peek(self, project_id: str) -> Project:
        return copy.deepcopy(self._data[project_id])


class FakeDirector:
    def __init__(self, turns: dict[str, DirectedTurn] | None = None, characters: Sequence[Character] = ()) -> None:
        self.turns = turns or {}
        self.characters = list(characters)
        self.calls: list[str] = []
        self.texts: list[str] = []

    async def direct_turn(self, turn: TranscriptTurn, project: Project) -> DirectedTurn:
        """Scripted by turn id. Live sessions prefix ids with a session tag ("s1-0"), so "0" matches too."""
        key = turn.id if turn.id in self.turns else turn.id.split("-", 1)[-1]
        self.calls.append(key)
        self.texts.append(turn.text)
        directed = self.turns[key]
        # Like the real adapter, cite the turn as stored.
        shots = tuple(replace(d, source_turn_ids=(turn.id,)) for d in directed.shots)
        return DirectedTurn(directed.new_characters, shots, directed.revisions)

    async def direct_story(self, project: Project) -> DirectedTurn:
        self.calls.append("direct_story")
        return DirectedTurn((), ())

    async def extract_characters(self, turns: Sequence[TranscriptTurn], known: Sequence[Character]) -> list[Character]:
        self.calls.append("extract_characters")
        return list(self.characters)

    async def interpret_edit(self, instruction: str, shot: Shot, cast: Sequence[Character]) -> EditIntent:
        self.calls.append(f"interpret_edit:{instruction}")
        return self.edit_intent

    edit_intent = EditIntent("girl", ("raincoat", "hood"), "make it red")


class InMemoryMediaStorage:
    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> MediaRef:
        self.files[key] = (data, content_type)
        return MediaRef(key)

    async def get(self, ref: MediaRef) -> bytes:
        return self.files[ref.key][0]

    async def delete(self, ref: MediaRef) -> None:
        self.files.pop(ref.key, None)


class FakeImageGeneration:
    """Stores a tiny fake image under `store_as`, like the real adapter does with model output."""

    def __init__(self, storage: InMemoryMediaStorage) -> None:
        self.storage = storage
        self.generated: list[ImageRequest] = []
        self.edits: list[tuple[str, str]] = []
        self.fail_next = False

    async def generate(self, request: ImageRequest, store_as: str) -> StoredImage:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("model unavailable")
        self.generated.append(request)
        return await self._store(store_as)

    async def edit(self, previous_response_id: str, prompt: str, quality: Quality, store_as: str) -> StoredImage:
        self.edits.append((previous_response_id, prompt))
        return await self._store(store_as)

    async def _store(self, key: str) -> StoredImage:
        n = len(self.generated) + len(self.edits)
        ref = await self.storage.put(key, f"image-{n}".encode(), "image/webp")
        return StoredImage(ref, f"resp_{n}", PANEL_SIZE)

    @property
    def calls(self) -> int:
        return len(self.generated) + len(self.edits)


class FakeSegmentation:
    def __init__(self, by_concept: dict[str, Segment] | None = None, at_point: Segment | None = None) -> None:
        self.by_concept = by_concept or {}
        self.at_point = at_point
        self.concept_calls: list[str] = []
        self.point_calls: list[Point] = []

    async def segment_concept(self, image: MediaRef, concept: str, store_prefix: str) -> list[Segment]:
        self.concept_calls.append(concept)
        return [self.by_concept[concept]] if concept in self.by_concept else []

    async def segment_point(self, image: MediaRef, point: Point, store_prefix: str) -> Segment | None:
        self.point_calls.append(point)
        return self.at_point


class FakeSpeechToText:
    """Consumes the audio, then emits `events` (or one TurnCompleted per turn)."""

    def __init__(self, turns: Sequence[TranscriptTurn] = (), events: Sequence[SpeechEvent] | None = None) -> None:
        self.turns = list(turns)
        self.events = list(events) if events is not None else [TurnCompleted(t) for t in turns]
        self.audio = bytearray()
        self.options: SpeechOptions | None = None

    async def stream(self, audio: AsyncIterator[bytes], options: SpeechOptions) -> AsyncIterator[SpeechEvent]:
        self.options = options
        async for chunk in audio:
            self.audio.extend(chunk)
        for event in self.events:
            yield event

    async def transcribe_file(self, wav: bytes, options: SpeechOptions) -> list[TranscriptTurn]:
        self.audio.extend(wav)
        self.options = options
        return list(self.turns)


LISTEN = object()  # in a ScriptedSpeech script: wait for the next audio chunk


class ScriptedSpeech(FakeSpeechToText):
    """Emits scripted events in step with the audio: each LISTEN step waits for the next chunk.

    `listening` is set while the fake waits at a LISTEN, after every earlier event was handled, so a test client
    can send a beat at an exact point in the transcript (see `paced`).
    """

    def __init__(self, script: Sequence[SpeechEvent | object]) -> None:
        super().__init__()
        self.script = list(script)
        self.listening = asyncio.Event()

    async def stream(self, audio: AsyncIterator[bytes], options: SpeechOptions) -> AsyncIterator[SpeechEvent]:
        self.options = options
        chunks = aiter(audio)
        for step in self.script:
            if step is LISTEN:
                self.listening.set()
                with contextlib.suppress(StopAsyncIteration):
                    self.audio.extend(await anext(chunks))
            else:
                yield step  # type: ignore[misc]
        self.listening.set()
        async for chunk in chunks:
            self.audio.extend(chunk)

    async def paced(self, *items: Any) -> AsyncIterator[Any]:
        """A client that sends each item once the transcript has caught up with the audio sent before it."""
        for item in items:
            await self.listening.wait()
            if isinstance(item, bytes):
                self.listening.clear()
            yield item


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


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, ProjectEvent]] = []

    async def publish(self, project_id: str, event: ProjectEvent) -> None:
        self.events.append((project_id, event))

    def of(self, kind: type) -> list[ProjectEvent]:
        return [e for _, e in self.events if isinstance(e, kind)]


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
        self.usage: list[UsageRecord] = []

    async def spent_by_project(self, project_id: str) -> float:
        return self.by_project[project_id]

    async def spent_on_day(self, day: str) -> float:
        return self.by_day[day]

    async def record(self, project_id: str, day: str, cost_usd: float, what: str) -> None:
        self.by_project[project_id] += cost_usd
        self.by_day[day] += cost_usd
        self.entries.append((project_id, day, cost_usd, what))

    async def record_usage(self, usage: UsageRecord) -> None:
        self.usage.append(usage)


class RecordingBudget:
    """BudgetGuard that never refuses and records every charge."""

    def __init__(self) -> None:
        self.charges: list[tuple[str, float, str]] = []

    async def charge(self, project_id: str, cost_usd: float, what: str) -> None:
        self.charges.append((project_id, cost_usd, what))

    @property
    def total(self) -> float:
        return sum(c for _, c, _ in self.charges)
