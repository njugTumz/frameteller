from __future__ import annotations

import io
import wave
from collections.abc import Callable
from pathlib import Path

import pytest

from frameteller.application.ports import ImageRequest, SpeechOptions, TurnCompleted
from frameteller.domain import Point, TranscriptTurn
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.local import LocalFileMediaStorage
from frameteller.infrastructure.meta import meta_client
from frameteller.infrastructure.meta.director import MetaSparkDirectorAdapter
from frameteller.infrastructure.meta.image import MetaImageAdapter
from frameteller.infrastructure.meta.sam import MetaSamAdapter
from frameteller.infrastructure.meta.voice import SAMPLE_RATE, MetaVoiceTranscribeAdapter, paced_pcm
from frameteller.infrastructure.resilience import ModelCaller
from tests.builders import project
from tests.fixtures import image

NARRATION = Path(__file__).resolve().parents[3] / "spikes" / "fixtures" / "narration.wav"
TURN = TranscriptTurn("t4", "Mira smiles and holds out her hand. The cat steps into the light.", 21600, 26800)
Reserve = Callable[[float], None]


async def test_director_single_turn(settings: Settings, caller: ModelCaller, reserve: Reserve) -> None:
    reserve(0.01)
    assert settings.director.endswith("-contributor")  # synthetic story only
    p = project(approved=True, shots=0)
    p.add_turn(TURN)

    out = await MetaSparkDirectorAdapter(meta_client(settings), caller, settings).direct_turn(TURN, p)

    assert out.shots
    assert {c for s in out.shots for c in s.character_ids} <= {"mira", "cat"}
    assert sum(s.duration_ms for s in out.shots) <= TURN.duration_ms


async def test_draft_panel_with_references(
    settings: Settings, caller: ModelCaller, reserve: Reserve, tmp_path: Path
) -> None:
    reserve(0.01)
    storage = LocalFileMediaStorage(tmp_path)
    mira = await storage.put("refs/mira.webp", image("ref_mira.webp"), "image/webp")
    cat = await storage.put("refs/cat.webp", image("ref_cat.webp"), "image/webp")
    request = ImageRequest(
        "Storyboard panel, pencil rough, no text. Medium shot: Mira kneels in a rainy alley at night and holds "
        "out her hand to the small grey cat with glowing eyes.",
        "low",
        "panel",
        (mira, cat),
    )

    out = await MetaImageAdapter(meta_client(settings), caller, storage, settings).generate(request, "panels/s1/r1")

    assert out.response_id
    assert out.size.width * 2 == out.size.height * 3  # 3:2 (ADR 0003)
    assert len(await storage.get(out.ref)) > 10_000


async def test_sam_point_select(settings: Settings, caller: ModelCaller, reserve: Reserve, tmp_path: Path) -> None:
    reserve(0.0025)
    storage = LocalFileMediaStorage(tmp_path)
    panel = await storage.put("panels/small.webp", image("panel_small.webp"), "image/webp")

    segment = await MetaSamAdapter(meta_client(settings), caller, storage, settings).segment_point(
        panel, Point(193, 129), "masks/obj"
    )

    assert segment is not None
    assert segment.cutout is not None
    assert segment.box.left <= 193 < segment.box.right


async def test_voice_streams_narration(settings: Settings, caller: ModelCaller, reserve: Reserve) -> None:
    if not NARRATION.exists():
        pytest.skip(f"no recording at {NARRATION.relative_to(NARRATION.parents[2])}: record it (mono, 16-bit, 24 kHz)")
    with wave.open(io.BytesIO(NARRATION.read_bytes())) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, SAMPLE_RATE)
        pcm = w.readframes(w.getnframes())
    reserve(0.18 * (len(pcm) / 48_000) / 3600 + 0.001)

    adapter = MetaVoiceTranscribeAdapter(caller, settings)
    events = [e async for e in adapter.stream(paced_pcm(pcm), SpeechOptions(keywords=("Mira",)))]

    turns = [e.turn for e in events if isinstance(e, TurnCompleted)]
    assert turns
    assert all(t.end_ms >= t.start_ms for t in turns)
