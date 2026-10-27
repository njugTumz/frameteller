"""End-to-end smoke test against a locally running backend. Spends real credits (about $0.05).

    cd backend && .venv/bin/uvicorn frameteller.interface.main:app --port 8000      # in one terminal
    cd backend && .venv/bin/python scripts/smoke_local.py                            # in another

Creates a project, streams spikes/fixtures/narration.wav over the session WebSocket at real-time pace,
prints events as they arrive, approves the proposed cast, renders draft panels for shots 1-2, clicks once
on panel 1, and prints latency per step and spend (read from the server's spend ledger for this project).
Starts nothing itself and never reads .env: the server holds the key.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
import urllib.request
import wave
from collections import defaultdict
from pathlib import Path
from typing import Any

import websockets

ROOT = Path(__file__).resolve().parents[2]
NARRATION = ROOT / "spikes" / "fixtures" / "narration.wav"
FRAME_MS = 80
BYTES_PER_MS = 48
T0 = time.perf_counter()


def stamp() -> str:
    return f"{time.perf_counter() - T0:7.2f}s"


def rest(base: str, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"null")
        except ValueError:
            return e.code, raw.decode(errors="replace")[:200]


def show(event: dict[str, Any]) -> str:
    kind = event["type"]
    if kind == "transcript.partial":
        return f"partial   {event['text'][-70:]!r}"
    if kind == "turn.completed":
        t = event["turn"]
        return f"TURN {t['id']}    {t['start_ms']}-{t['end_ms']} ms  {t['text'][:80]!r}"
    if kind == "shot.created":
        s = event["shot"]
        return (
            f"SHOT {s['number']:<4} {s['framing']:<9} {s['character_ids']} {s['action'][:60]!r} ({s['duration_ms']} ms)"
        )
    if kind == "cast.proposed":
        return "CAST      " + ", ".join(f"{c['id']} ({c['description'][:50]}...)" for c in event["characters"])
    if kind == "job.updated":
        extra = f" {event['message']}" if event.get("message") else ""
        return f"job       {event['kind']} {event['status']} {event.get('shot_id') or ''}{extra}"
    return f"{kind:<9} {json.dumps({k: v for k, v in event.items() if k != 'type'})}"


class Session:
    def __init__(self, ws: Any) -> None:
        self.ws = ws
        self.events: list[dict[str, Any]] = []
        self.partials = 0
        self.changed = asyncio.Event()

    async def listen(self) -> None:
        async for raw in self.ws:
            event = json.loads(raw)
            self.events.append(event)
            if event["type"] == "transcript.partial":
                self.partials += 1
                if self.partials % 15 != 1:  # print a sample, not all ~90
                    self.changed.set()
                    continue
            print(f"{stamp()}  {show(event)}", flush=True)
            self.changed.set()

    async def wait_for(self, done: Any, timeout: float) -> None:
        async with asyncio.timeout(timeout):
            while not done(self.events):
                self.changed.clear()
                await self.changed.wait()


def jobs_done(kind: str, keys: set[str]) -> Any:
    def done(events: list[dict[str, Any]]) -> bool:
        finished = {
            e["key"]
            for e in events
            if e["type"] == "job.updated" and e["kind"] == kind and e["status"] in ("succeeded", "failed")
        }
        return keys <= finished

    return done


async def main(base: str, data_dir: Path) -> int:
    timings: dict[str, float] = {}
    with wave.open(io.BytesIO(NARRATION.read_bytes())) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24_000), "need mono 16-bit 24 kHz"
        pcm = w.readframes(w.getnframes())
    print(f"narration {len(pcm) / 48_000:.1f} s; backend {base}")

    status, health = rest(base, "GET", "/readyz")
    print(f"{stamp()}  readyz {status} {health}")
    status, project = rest(base, "POST", "/projects", {"title": "Smoke: the lantern cat"})
    assert status == 201, project
    pid = project["id"]
    print(f"{stamp()}  project {pid}")

    ws_url = base.replace("http", "ws", 1) + f"/ws/projects/{pid}/session"
    async with websockets.connect(ws_url, max_size=None) as ws:
        session = Session(ws)
        listener = asyncio.create_task(session.listen())
        await ws.send(json.dumps({"mode": "narrate", "keywords": ["Mira"]}))

        started = time.perf_counter()
        step = FRAME_MS * BYTES_PER_MS
        for i, offset in enumerate(range(0, len(pcm), step)):
            await asyncio.sleep(max(0.0, started + i * FRAME_MS / 1000 - time.perf_counter()))
            await ws.send(pcm[offset : offset + step])
        await ws.send(json.dumps({"type": "end"}))
        sent_at = time.perf_counter()

        await session.wait_for(lambda ev: any(e["type"] == "session.ended" for e in ev), 120)
        timings["narration end -> session.ended"] = time.perf_counter() - sent_at
        cast_keys = {e["key"] for e in session.events if e["type"] == "job.updated" and e["kind"] == "generate_cast"}
        await session.wait_for(jobs_done("generate_cast", cast_keys), 180)
        timings["narration end -> cast sheets drawn"] = time.perf_counter() - sent_at

        t = time.perf_counter()
        status, review = rest(base, "POST", f"/projects/{pid}/cast/approve", {})
        print(f"{stamp()}  approve {status} {review}")
        if not (status == 200 and review["approved"]):
            print("cast not approved; stopping")
            return 1

        tickets = []
        for n in (1, 2):
            status, ticket = rest(base, "POST", f"/projects/{pid}/shots/{n}/panel", {"quality": "draft"})
            print(f"{stamp()}  render shot {n}: {status} {ticket}")
            tickets.append(ticket)
        await session.wait_for(jobs_done("generate_panel", {tk["key"] for tk in tickets}), 240)
        timings["draft panels 1-2 (parallel)"] = time.perf_counter() - t

        t = time.perf_counter()
        shot1 = tickets[0]["shot_id"]
        pre_keys = {f"pre_segment_panel:{pid}:{shot1}:r1"}
        await session.wait_for(jobs_done("pre_segment_panel", pre_keys), 120)
        timings["pre-segment panel 1 (after its render)"] = time.perf_counter() - t

        _, project = rest(base, "GET", f"/projects/{pid}")
        panel = project["shots"][0]["panel"]
        width, height = panel["width"], panel["height"]
        if panel["masks"]:
            box = panel["masks"][0]["box"]
            x, y = (
                (box["left"] + box["right"]) // 4,
                (box["top"] + box["bottom"]) // 4,
            )  # centre, on a half-size preview
        else:
            x, y = width // 4, height // 4
        t = time.perf_counter()
        click = {"x": x, "y": y, "preview_width": width // 2, "preview_height": height // 2}
        status, selection = rest(base, "POST", f"/projects/{pid}/shots/1/panel/select", click)
        timings["click-select on panel 1"] = time.perf_counter() - t
        if status == 200:
            m = selection["mask"]
            print(f"{stamp()}  select {click} -> cached={selection['cached']} {m['id']} {m['label']!r} box={m['box']}")
        else:
            print(f"{stamp()}  select {click} -> {status} {selection}")

        await asyncio.sleep(0.5)
        listener.cancel()
        await asyncio.gather(listener, return_exceptions=True)

    shots = [e for e in session.events if e["type"] == "shot.created"]
    turns = [e for e in session.events if e["type"] == "turn.completed"]
    print(f"\n{len(turns)} turns, {len(shots)} shots, {session.partials} partials, project {pid}")
    print("\nlatency")
    for name, seconds in timings.items():
        print(f"  {name:<42} {seconds:6.1f} s")
    print(f"  {'total wall time':<42} {time.perf_counter() - T0:6.1f} s")

    by_model: dict[str, list[float]] = defaultdict(list)
    ledger = data_dir / "spend.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
    for r in rows:
        if r["type"] == "usage" and r.get("project_id") == pid:
            by_model[f"{r['model']} {r['operation']}"].append(r["cost_usd"])
    print("\nspend (server ledger, this project)")
    for name, costs in sorted(by_model.items()):
        print(f"  {name:<44} {len(costs):>3} calls  ${sum(costs):.4f}")
    print(f"  {'total':<54} ${sum(sum(c) for c in by_model.values()):.4f}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[1] / ".data")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.base.rstrip("/"), args.data_dir)))
