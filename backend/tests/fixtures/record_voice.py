"""Record the voice contract fixtures from real sessions on spikes/fixtures/narration.wav (about $0.008).

    cd backend && .venv/bin/python -m tests.fixtures.record_voice OUT_DIR

Runs one realtime session per mode (ENDPOINTING, DIARIZATION) and one file transcription. Writes the raw
server events with receive times to OUT_DIR (outside the repo) for measurement; `--write` also writes the
scrubbed event streams to tests/fixtures/meta/; `--from-raw` reuses OUT_DIR/voice_raw.json
instead of paying for new sessions. Audio is never written anywhere. The key comes from .env via
the settings class and is never printed.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any

import websockets

from frameteller.application.ports import SpeechMode, SpeechOptions
from frameteller.infrastructure.config import load_settings
from frameteller.infrastructure.meta.voice import MetaVoiceTranscribeAdapter, _multipart, paced_pcm
from frameteller.infrastructure.resilience import Breakers, ModelCaller
from tests.fakes import InMemorySpendLedger
from tests.fixtures import META, Scrubber

NARRATION = Path(__file__).resolve().parents[3] / "spikes" / "fixtures" / "narration.wav"
OPTIONS = {
    "narration": SpeechOptions(SpeechMode.NARRATION, keywords=("Mira",)),
    "co_direction": SpeechOptions(SpeechMode.CO_DIRECTION, keywords=("Mira",)),
}


async def session(adapter: MetaVoiceTranscribeAdapter, url: str, pcm: bytes, options: SpeechOptions) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    async with websockets.connect(url, max_size=None) as ws:
        await ws.send(json.dumps(adapter._handshake(options)))
        ack = json.loads(await ws.recv())
        started = time.perf_counter()

        async def send() -> None:
            async for chunk in paced_pcm(pcm):
                await ws.send(chunk)
            events.append({"sent_end_stream_at_ms": round((time.perf_counter() - started) * 1000)})
            await ws.send(json.dumps({"type": "endStream"}))

        sender = asyncio.create_task(send())
        async for raw in ws:
            if isinstance(raw, str):
                events.append({"t_ms": round((time.perf_counter() - started) * 1000), "event": json.loads(raw)})
        await sender
        return {"ack": ack, "close_code": ws.close_code, "events": events}


async def main(out: Path, write: bool, from_raw: bool) -> None:
    settings = load_settings()
    wav = NARRATION.read_bytes()
    with wave.open(io.BytesIO(wav)) as w:
        pcm = w.readframes(w.getnframes())
    ledger = InMemorySpendLedger()
    adapter = MetaVoiceTranscribeAdapter(ModelCaller(ledger, Breakers()), settings)
    out.mkdir(parents=True, exist_ok=True)

    raw: dict[str, Any] = {}
    if from_raw:
        raw = json.loads((out / "voice_raw.json").read_text())
    for name, options in OPTIONS.items():
        if name in raw:
            continue
        print(f"realtime {name} ...")
        raw[name] = await session(adapter, settings.meta_realtime_url, pcm, options)
        print(f"  {len(raw[name]['events'])} events, close {raw[name]['close_code']}")

    (out / "voice_raw.json").write_text(json.dumps(raw, indent=1))  # keep what was paid for
    cached = out / "voice_file.json"
    if cached.exists():
        raw["file"] = json.loads(cached.read_text())
    else:
        print("file transcribe ...")
        body, content_type = _multipart(
            {"model": settings.asr_model, "audioEncoding": "WAV", "keywords": ["Mira"]}, wav
        )
        req = urllib.request.Request(
            settings.meta_base_url + "/asr/transcribe",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {settings.model_api_key.get_secret_value()}",
                "Content-Type": content_type,
            },
        )
        with urllib.request.urlopen(req, timeout=300) as r:
            raw["file"] = json.loads(r.read())
        cached.write_text(json.dumps(raw["file"], indent=1))
    (out / "voice_raw.json").write_text(json.dumps(raw, indent=1))
    print(f"raw events written to {out / 'voice_raw.json'}")

    if write:
        scrub = Scrubber()
        fixture = {
            "_source": "Recorded once from real sessions on spikes/fixtures/narration.wav (our own narration of the "
            "synthetic story). Event streams only, no audio; session ids scrubbed.",
            "ack": scrub.value(raw["narration"]["ack"]),
        }
        for name in OPTIONS:
            fixture[name] = [scrub.value(e["event"]) for e in raw[name]["events"] if "event" in e]
        fixture["file"] = scrub.value(raw["file"])
        (META / "voice_realtime.json").write_text(json.dumps(fixture, indent=1) + "\n")
        print("fixture written to tests/fixtures/meta/voice_realtime.json")


if __name__ == "__main__":
    sys.exit(asyncio.run(main(Path(sys.argv[1]), "--write" in sys.argv, "--from-raw" in sys.argv)))
