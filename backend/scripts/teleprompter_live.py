"""Teleprompter live check (ADR 0015): read a recording against a script and see where each paragraph is cut.

    cd backend && .venv/bin/python scripts/teleprompter_live.py --api https://<staging> \\
        --script ../spikes/fixtures/story.txt

Creates a project, starts a teleprompter session with the script (one line or paragraph per beat), streams
spikes/fixtures/narration.wav at real-time pace and presses nothing: every cut is automatic. Prints, for each
paragraph, the audio position of the cut, when it arrived, and the turn and shots it became. Spends about
USD 0.03 (Voice Transcribe for 49 s, the director, and cast sheets). Never reads .env: the server holds the key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any

import websockets

ROOT = Path(__file__).resolve().parents[2]
NARRATION = ROOT / "spikes" / "fixtures" / "narration.wav"
FRAME_MS = 80
BYTES_PER_MS = 48
T0 = time.perf_counter()


def now() -> float:
    return time.perf_counter() - T0


def create(api: str, title: str) -> str:
    req = urllib.request.Request(
        f"{api}/projects",
        data=json.dumps({"title": title, "style": "pencil"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return str(json.loads(r.read())["id"])


def paragraphs(text: str) -> str:
    """One beat per line, as the studio would take a pasted script with blank lines between paragraphs."""
    return "\n\n".join(line.strip() for line in text.splitlines() if line.strip())


async def run(api: str, script: str, keywords: list[str], project: str | None = None) -> dict[str, Any]:
    project = project or create(api, "Teleprompter check")
    with wave.open(str(NARRATION)) as w:
        pcm = w.readframes(w.getnframes())
    frame = FRAME_MS * BYTES_PER_MS
    events: list[tuple[float, dict[str, Any]]] = []
    sent_ms = 0
    url = api.replace("https://", "wss://").replace("http://", "ws://") + f"/ws/projects/{project}/session"
    async with websockets.connect(url, max_size=None) as ws:
        start = {"mode": "teleprompter", "script": paragraphs(script), "keywords": keywords, "keep_audio": True}
        await ws.send(json.dumps(start))

        async def read() -> None:
            async for raw in ws:
                e = json.loads(raw)
                events.append((now(), {**e, "_sent_ms": sent_ms}))
                if e["type"] == "session.ended":
                    return

        reader = asyncio.create_task(read())
        while not any(e["type"] == "session.started" for _, e in events):
            await asyncio.sleep(0.02)
        began = time.perf_counter()
        for i in range(0, len(pcm), frame):
            await ws.send(pcm[i : i + frame])
            sent_ms = (i + frame) // BYTES_PER_MS
            # Real time: never ahead of the clock (the transcriber rejects streams that run ahead).
            await asyncio.sleep(max(0.0, began + sent_ms / 1000 - time.perf_counter()))
        await asyncio.sleep(1.5)  # a reader's last pause
        await ws.send(json.dumps({"type": "end"}))
        await asyncio.wait_for(reader, 180)
    return {"project": project, "events": events}


def report(result: dict[str, Any]) -> None:
    events = result["events"]
    accepted = next(e for _, e in events if e["type"] == "script.accepted")
    texts = [p["narration"] for ep in accepted["episodes"] for p in ep["paragraphs"]]
    print(f"project {result['project']}: {len(texts)} paragraphs")
    turns = {e["turn"]["id"]: e["turn"] for _, e in events if e["type"] == "turn.completed"}
    advanced = [e for _, e in events if e["type"] == "teleprompter.advanced"]
    order = list(turns.values())
    for n, e in enumerate(advanced):
        turn = order[n] if n < len(order) else None
        span = f"{turn['start_ms'] / 1000:5.1f}-{turn['end_ms'] / 1000:5.1f} s" if turn else "     (none)    "
        lag = (e["_sent_ms"] - turn["end_ms"]) / 1000 if turn else float("nan")
        sent = e["_sent_ms"] / 1000
        print(f"  {n + 1}. cut {span}  arrived with {sent:5.1f} s sent (+{lag:3.1f} s)  {texts[n][:60]}")
    shots = [e["shot"] for _, e in events if e["type"] == "shot.created"]
    errors = [e["message"] for _, e in events if e["type"] == "error"]
    ended = next(e for _, e in events if e["type"] == "session.ended")
    print(f"  turns {ended['turns']}, shots {ended['shots']} ({len(shots)} created), errors: {errors or 'none'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--keywords", default="Mira")
    parser.add_argument("--project", help="tell it again in an existing project (a new session continues it)")
    args = parser.parse_args()
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    report(asyncio.run(run(args.api.rstrip("/"), args.script.read_text(), keywords, args.project)))


if __name__ == "__main__":
    main()
