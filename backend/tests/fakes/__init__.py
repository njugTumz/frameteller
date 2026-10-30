"""In-memory fakes for every application port. No network, no disk."""

from __future__ import annotations

import asyncio
import contextlib
import copy
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from frameteller.application.audio import wav_bytes
from frameteller.application.errors import ModelUnavailableError, ProjectNotFoundError
from frameteller.application.events import ProjectEvent
from frameteller.application.ports import (
    CaptionTrack,
    CutoutLayer,
    DirectedTurn,
    EditIntent,
    EditRequest,
    ImageRequest,
    Job,
    Progress,
    ReviewRequest,
    Segment,
    SpeechEvent,
    SpeechOptions,
    SpokenClip,
    StoredImage,
    TurnCompleted,
    UsageRecord,
    Voice,
)
from frameteller.application.rubrics import Rubric, parse_rubric
from frameteller.domain import (
    Animatic,
    Character,
    Decision,
    Gallery,
    Issue,
    MediaRef,
    Point,
    Project,
    Shot,
    Size,
    TranscriptTurn,
    Verdict,
)

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
        return replace(directed, shots=shots)

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

    async def exists(self, ref: MediaRef) -> bool:
        return ref.key in self.files


class FakeImageGeneration:
    """Stores a tiny fake image under `store_as`, like the real adapter does with model output."""

    def __init__(self, storage: InMemoryMediaStorage) -> None:
        self.storage = storage
        self.generated: list[ImageRequest] = []
        self.edits: list[EditRequest] = []
        self.fail_next = False
        self.refuse: list[BaseException] = []  # raised, in order, by the next generate calls

    async def generate(self, request: ImageRequest, store_as: str) -> StoredImage:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("model unavailable")
        if self.refuse:
            self.generated.append(request)
            raise self.refuse.pop(0)
        self.generated.append(request)
        return await self._store(store_as)

    async def edit(self, request: EditRequest, store_as: str) -> StoredImage:
        self.edits.append(request)
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
        self.rendered: list[tuple[Animatic, dict[str, bytes], dict[str, bytes], CaptionTrack | None]] = []

    async def render(
        self,
        animatic: Animatic,
        frames: Mapping[str, bytes],
        recordings: Mapping[str, bytes],
        *,
        captions: CaptionTrack | None = None,
        on_progress: Progress | None = None,
    ) -> bytes:
        self.rendered.append((animatic, dict(frames), dict(recordings), captions))
        if on_progress is not None:
            for done in (0.02, 0.3, 0.6, 1.0):
                await on_progress(done)
        return b"\x00\x00\x00\x18ftypmp42"


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


class InMemoryVisitorQuota:
    def __init__(self) -> None:
        self.counts: dict[tuple[str, str, str], int] = defaultdict(int)

    async def used(self, visitor: str, day: str, kind: str) -> int:
        return self.counts[(visitor, day, kind)]

    async def add(self, visitor: str, day: str, kind: str, amount: int = 1) -> None:
        self.counts[(visitor, day, kind)] += amount


class InMemoryShareIndex:
    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}

    async def put(self, token: str, project_id: str) -> None:
        self.tokens[token] = project_id

    async def find(self, token: str) -> str | None:
        return self.tokens.get(token)

    async def delete(self, token: str) -> None:
        self.tokens.pop(token, None)


class FakeCompositor:
    """Records what it was asked to paste and returns a recognisable image."""

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, list[CutoutLayer], Size]] = []

    async def compose(self, background: bytes, layers: Sequence[CutoutLayer], size: Size) -> bytes:
        self.calls.append((background, list(layers), size))
        return b"composite-" + background


class RecordingBudget:
    """BudgetGuard that never refuses and records every charge."""

    def __init__(self) -> None:
        self.charges: list[tuple[str, float, str]] = []

    async def charge(self, project_id: str, cost_usd: float, what: str) -> None:
        self.charges.append((project_id, cost_usd, what))

    @property
    def total(self) -> float:
        return sum(c for _, c, _ in self.charges)


def verdict(
    decision: Decision = Decision.PASS,
    *issues: Issue,
    confidence: float = 0.9,
    fix: str = "",
    target: str = "",
    parts: tuple[str, ...] = (),
    model: str = "fake-reviewer",
) -> Verdict:
    return Verdict(decision, confidence, issues, fix, target, parts, model, 5, (("panel-continuity", "abc123"),))


PASS = verdict()


class FakeReviewer:
    """ReviewerPort that answers from a script (one verdict per call, the last one repeating), else passes."""

    def __init__(self, *verdicts: Verdict | Exception) -> None:
        self.verdicts: list[Verdict | Exception] = list(verdicts)
        self.requests: list[ReviewRequest] = []

    async def review(self, request: ReviewRequest) -> Verdict:
        self.requests.append(request)
        if not self.verdicts:
            return PASS
        answer = self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def rubric_text(rubric_id: str, *rules: tuple[str, str]) -> str:
    rows = "\n".join(f"| {rule_id} | {severity} | test {rule_id} |" for rule_id, severity in rules)
    head = f"---\nid: {rubric_id}\nversion: 1\n---\n# {rubric_id}\nGuidance.\n\n## Rules\n\n"
    return f"{head}| id | severity | test |\n|---|---|---|\n{rows}\n"


class InMemoryRubricLibrary:
    """The pipeline rubrics (and the gallery's) with one blocker, one major and one minor rule each."""

    def __init__(self) -> None:
        prefixes = {"cast": "CAST", "panel-continuity": "CONT", "shot": "SHOT", "edit": "EDIT", "gallery": "GAL"}
        self.rubrics: dict[str, Rubric] = {
            rid: parse_rubric(rubric_text(rid, (f"{p}-01", "blocker"), (f"{p}-02", "major"), (f"{p}-03", "minor")))
            for rid, p in prefixes.items()
        }

    def get(self, rubric_id: str) -> Rubric:
        return self.rubrics[rubric_id]


class FakeSpeechSynthesis:
    """Speaks 10 ms of silence per character, stored as 24 kHz WAV like Azure's."""

    def __init__(self, storage: InMemoryMediaStorage, fail: bool = False) -> None:
        self.storage = storage
        self.calls: list[tuple[str, str, str]] = []
        self.fail = fail

    async def voices(self) -> list[Voice]:
        return [
            Voice("en-US-AvaMultilingualNeural", "Ava", "Female", "en-US", ("en-US", "fr-FR")),
            Voice("en-US-BrandonMultilingualNeural", "Brandon", "Male", "en-US", ("en-US", "fr-FR")),
        ]

    async def synthesize(self, text: str, voice: str, language: str, store_as: str) -> SpokenClip:
        if self.fail:
            raise ModelUnavailableError("azure-tts")
        self.calls.append((text, voice, language))
        ref = await self.storage.put(store_as, wav_bytes(b"\x00\x00" * 240 * len(text)), "audio/wav")
        return SpokenClip(ref, len(text) * 10)


class FakeTranslator:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[list[str], str]] = []
        self.fail = fail

    async def translate(self, texts: Sequence[str], language: str) -> list[str]:
        if self.fail:
            raise ModelUnavailableError("muse-spark-1.3")
        self.calls.append((list(texts), language))
        return [f"[{language}] {t}" for t in texts]


class InMemoryGalleryRepository:
    def __init__(self) -> None:
        self.gallery = Gallery()

    async def get(self) -> Gallery:
        return copy.deepcopy(self.gallery)

    async def update[T](self, change: Callable[[Gallery], T]) -> T:
        gallery = copy.deepcopy(self.gallery)
        result = change(gallery)  # a change that raises saves nothing
        self.gallery = gallery
        return result


class FakeSharePreview:
    def __init__(self) -> None:
        self.sheets: list[tuple[str, int]] = []

    async def contact_sheet(self, title: str, panels: Sequence[bytes]) -> bytes:
        self.sheets.append((title, len(panels)))
        return b"\x89PNG-sheet"
