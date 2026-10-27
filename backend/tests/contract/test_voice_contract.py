"""Voice adapter against a local server replaying event streams recorded from real sessions.

tests/fixtures/meta/voice_realtime.json holds the server events of one ENDPOINTING and one DIARIZATION session
on spikes/fixtures/narration.wav, plus one file transcription (recorded by tests/fixtures/record_voice.py).
"""

from __future__ import annotations

import asyncio
import io
import json
import threading
import wave
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, serve

from frameteller.application.errors import ModelRejectedError, ModelUnavailableError
from frameteller.application.ports import (
    AudioProgress,
    PartialTranscript,
    SpeakerIdentified,
    SpeechMode,
    SpeechOptions,
    TurnCompleted,
    TurnEnded,
    TurnStarted,
)
from frameteller.infrastructure.config import Settings, load_settings
from frameteller.infrastructure.meta.voice import BYTES_PER_MS, MetaVoiceTranscribeAdapter, paced_pcm
from frameteller.infrastructure.resilience import ModelCaller
from tests.contract.conftest import FAKE_KEY
from tests.fakes import InMemorySpendLedger
from tests.fixtures import META

SCRIPT = json.loads((META / "voice_realtime.json").read_text())


@dataclass
class FakeAsr:
    events: list[dict[str, Any]]
    close_code: int = 1000
    handshake: dict[str, Any] = field(default_factory=dict)
    audio: bytearray = field(default_factory=bytearray)
    ended: bool = False

    async def __call__(self, ws: ServerConnection) -> None:
        self.handshake = json.loads(await ws.recv())
        await ws.send(json.dumps(SCRIPT["ack"]))
        async for message in ws:
            if isinstance(message, bytes):
                self.audio.extend(message)
            elif json.loads(message) == {"type": "endStream"}:
                self.ended = True
                break
        for ev in self.events:
            await ws.send(json.dumps(ev))
        await ws.close(self.close_code, "done" if self.close_code == 1000 else "server error")


async def chunks(n: int, size: int = 4800) -> AsyncIterator[bytes]:
    for _ in range(n):
        yield b"\x00" * size


async def run(server: FakeAsr, settings: Settings, caller: ModelCaller, options: SpeechOptions) -> list[Any]:
    async with serve(server, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        local = settings.model_copy(update={"meta_realtime_url": f"ws://127.0.0.1:{port}"})
        adapter = MetaVoiceTranscribeAdapter(caller, local)
        return [ev async for ev in adapter.stream(chunks(5), options)]


async def test_narration_session_streams_typed_events(
    settings: Settings, caller: ModelCaller, ledger: InMemorySpendLedger
) -> None:
    server = FakeAsr(SCRIPT["narration"])

    events = await run(server, settings, caller, SpeechOptions(keywords=("Mira",), language_bias="en"))

    assert server.handshake == {
        "model": "muse-voice-transcribe-1.0",
        "authorization": {"accessToken": f"Bearer {FAKE_KEY}"},
        "audioEncoding": "PCM_24KHZ",
        "mode": "ENDPOINTING",
        "partialMode": "CUMULATIVE",
        "keywords": ["Mira"],
        "languageBias": "en",
    }
    assert len(server.audio) == 5 * 4800
    assert server.ended
    # The real session merged the six spoken paragraphs into four turns (Day 2 findings).
    turns = [e.turn for e in events if isinstance(e, TurnCompleted)]
    assert [(t.id, t.start_ms, t.end_ms) for t in turns] == [
        ("0", 5340, 15260),
        ("1", 15420, 20860),
        ("2", 21660, 39260),
        ("3", 40300, 45580),
    ]
    assert turns[1].text == "She hears a tiny sound under a wooden crate she kneels down and looks"
    assert all(t.speaker is None for t in turns)
    # Every turn arrives as start, partials, end, complete; audioProgress and the final empty partial are dropped.
    progress = [e.processed_ms for e in events if isinstance(e, AudioProgress)]
    assert progress == sorted(progress)
    assert progress
    story = [e for e in events if not isinstance(e, AudioProgress)]
    assert [type(e) for e in story[:2]] == [TurnStarted, PartialTranscript]
    assert sum(isinstance(e, TurnStarted) for e in events) == sum(isinstance(e, TurnEnded) for e in events) == 4
    assert all(e.text for e in events if isinstance(e, PartialTranscript))
    [usage] = ledger.usage
    assert usage.operation == "stream"
    assert usage.ok
    assert usage.cost_usd == pytest.approx(0.18 / 3600)  # 500 ms of audio billed as one whole second


async def test_co_direction_labels_speakers(settings: Settings, caller: ModelCaller) -> None:
    server = FakeAsr(SCRIPT["co_direction"])

    events = await run(server, settings, caller, SpeechOptions(mode=SpeechMode.CO_DIRECTION, keywords=("Mira",)))

    assert server.handshake["mode"] == "DIARIZATION"
    # A real speaker event has no turnId and arrives while its turn is open; one narrator means one long turn.
    assert [e for e in events if isinstance(e, SpeakerIdentified)] == [SpeakerIdentified("0", "A")]
    [turn] = [e.turn for e in events if isinstance(e, TurnCompleted)]
    assert (turn.speaker, turn.start_ms, turn.end_ms) == ("A", 5500, 47660)


async def test_abnormal_close_is_a_model_error(
    settings: Settings, caller: ModelCaller, ledger: InMemorySpendLedger
) -> None:
    server = FakeAsr(SCRIPT["narration"][:3], close_code=1011)

    with pytest.raises(ModelUnavailableError):
        await run(server, settings, caller, SpeechOptions())
    assert [u.ok for u in ledger.usage] == [False]


async def test_paced_pcm_sends_at_real_time() -> None:
    pcm = b"\x00" * (BYTES_PER_MS * 240)  # 240 ms
    loop = asyncio.get_running_loop()
    started = loop.time()
    frames = [f async for f in paced_pcm(pcm, frame_ms=80)]
    assert [len(f) for f in frames] == [80 * BYTES_PER_MS] * 3
    assert loop.time() - started >= 0.15  # frames 2 and 3 wait for their slot


# ---- file fallback ----


def wav(rate: int = 24_000, channels: int = 1, ms: int = 500) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * channels * (rate * ms // 1000))
    return buf.getvalue()


@pytest.fixture
def file_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[Settings, list[dict[str, Any]]]]:
    received: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append({"path": self.path, "auth": self.headers["Authorization"], "body": body})
            payload = json.dumps(SCRIPT["file"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: Any) -> None:
            return None

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.chdir(tmp_path)
    settings = load_settings(model_api_key=FAKE_KEY, meta_base_url=f"http://127.0.0.1:{httpd.server_port}/v1")
    yield settings, received
    httpd.shutdown()


async def test_file_fallback_posts_multipart_and_returns_turns(
    file_api: tuple[Settings, list[dict[str, Any]]], caller: ModelCaller, ledger: InMemorySpendLedger
) -> None:
    settings, received = file_api
    adapter = MetaVoiceTranscribeAdapter(caller, settings)

    turns = await adapter.transcribe_file(wav(), SpeechOptions(keywords=("Mira",)))

    assert [(t.id, t.start_ms, t.end_ms) for t in turns] == [("0", 5340, 9180), ("1", 9740, 15260), ("2", 15740, 45580)]
    assert turns[1].text.startswith("Mira a girl in a yellow raincoat")
    [req] = received
    assert req["path"] == "/v1/asr/transcribe"
    assert req["auth"] == f"Bearer {FAKE_KEY}"
    assert b'name="request"' in req["body"]
    assert b'name="audio"' in req["body"]
    assert b'"mode": "ENDPOINTING"' in req["body"]
    assert b'"audioEncoding": "WAV"' in req["body"]
    assert b'"keywords": ["Mira"]' in req["body"]
    assert FAKE_KEY.encode() not in req["body"]  # auth only in the header for the file endpoint
    assert ledger.usage[0].cost_usd == pytest.approx(0.18 / 3600)


@pytest.mark.parametrize(
    ("audio", "message"),
    [
        (b"not a wav", "not a WAV"),
        (wav(channels=2), "mono"),
        (wav(rate=44_100), "16 or 24 kHz"),
        (wav(rate=16_000, ms=10 * 60 * 1000 + 100), "10 minutes"),
    ],
)
async def test_file_fallback_rejects_unsupported_audio(
    settings: Settings, caller: ModelCaller, audio: bytes, message: str
) -> None:
    adapter = MetaVoiceTranscribeAdapter(caller, settings)
    with pytest.raises(ModelRejectedError, match=message):
        await adapter.transcribe_file(audio, SpeechOptions())
