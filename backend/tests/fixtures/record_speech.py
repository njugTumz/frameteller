"""Record the Azure Text-to-Speech contract fixtures once (costs well under $0.01).

    cd backend && .venv/bin/python -m tests.fixtures.record_speech

The key is read from ~/.config/frameteller/speech.key (or AZURE_SPEECH_KEY) and is never printed or written.
Writes tests/fixtures/azure/: the multilingual neural voices from the voice list (the full list is large) and
one short French synthesis, cut to its first half second with its full length noted.
"""

from __future__ import annotations

import io
import json
import os
import sys
import wave
from pathlib import Path

import httpx2

from frameteller.infrastructure.azure.speech import OUTPUT_FORMAT, ssml

HERE = Path(__file__).parent / "azure"
KEY_FILE = Path.home() / ".config" / "frameteller" / "speech.key"
REGION = os.environ.get("AZURE_SPEECH_REGION", "eastus2")
BASE = f"https://{REGION}.tts.speech.microsoft.com"
TEXT = "La nuit tombe sur les toits."
VOICE = "en-US-BrandonMultilingualNeural"
KEEP_MS = 500


def key() -> str:
    value = os.environ.get("AZURE_SPEECH_KEY") or (KEY_FILE.read_text().strip() if KEY_FILE.exists() else "")
    if not value:
        sys.exit(f"No Speech key: store it in {KEY_FILE} (see docs/runbook.md).")
    return value


def main() -> None:
    headers = {"Ocp-Apim-Subscription-Key": key(), "User-Agent": "frameteller"}
    HERE.mkdir(exist_ok=True)
    with httpx2.Client(timeout=30) as http:
        r = http.get(f"{BASE}/cognitiveservices/voices/list", headers=headers)
        r.raise_for_status()
        voices = [v for v in r.json() if "Multilingual" in v.get("ShortName", "") and v.get("VoiceType") == "Neural"]
        (HERE / "voices_list.json").write_text(json.dumps(voices, indent=1, ensure_ascii=False) + "\n")

        r = http.post(
            f"{BASE}/cognitiveservices/v1",
            content=ssml(TEXT, VOICE, "fr-FR").encode(),
            headers={**headers, "Content-Type": "application/ssml+xml", "X-Microsoft-OutputFormat": OUTPUT_FORMAT},
        )
        r.raise_for_status()
    with wave.open(io.BytesIO(r.content)) as w:
        params, frames = w.getparams(), w.getnframes()
        kept = w.readframes(w.getframerate() * KEEP_MS // 1000)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        w.writeframes(kept)
    (HERE / "synthesize_fr.wav").write_bytes(out.getvalue())
    meta = {
        "text": TEXT,
        "voice": VOICE,
        "language": "fr-FR",
        "content_type": r.headers.get("content-type", ""),
        "channels": params.nchannels,
        "sample_width": params.sampwidth,
        "rate": params.framerate,
        "full_duration_ms": frames * 1000 // params.framerate,
    }
    (HERE / "synthesize_fr.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"recorded {len(voices)} multilingual voices and {meta['full_duration_ms']} ms of speech")


if __name__ == "__main__":
    main()
