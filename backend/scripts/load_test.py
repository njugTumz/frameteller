"""Load test (ADR 0016): many visitors at once against a local stack whose Meta models are fakes. Spends nothing.

    cd backend && .venv/bin/python scripts/load_test.py --visitors 50

Starts the real app (routes, waiting room, gates, job queue, budget, local storage, Pillow, ffmpeg) in a
subprocess on --port, with fake adapters for Voice Transcribe, Spark, Muse Image, SAM and the supervisor that
sleep for the latencies measured on staging and return real-sized images. Then each visitor, arriving over
--ramp seconds with its own browser id: creates a project, narrates --narration seconds of PCM at real-time
pace with a beat every few seconds, waits for the cast sheets, approves the cast, draws every shot as a draft,
and exports the animatic (real ffmpeg, burned captions).

Reports latency per step (p50, p95, max), the longest line at each gate (GET /admin/overview), and the server's
CPU and memory (the process and its ffmpeg children, from /proc). --scale divides every fake latency, for a
quick run. The per-IP rate limits are raised, since every visitor here shares 127.0.0.1. Never reads .env.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import os
import secrets
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

FRAME_MS = 80
BYTES_PER_MS = 48  # PCM 24 kHz s16le mono
TICK = os.sysconf("SC_CLK_TCK")
PAGE = os.sysconf("SC_PAGE_SIZE")

# Latencies of the real models, seconds (staging logs, Oct 28-29; draft panels are reasoning_strength low).
LATENCY = {"turn": 3.0, "cast": 4.0, "image": 18.0, "sam": 4.0, "review": 3.0, "edit": 20.0}
TURN_EVERY_MS = 6000  # a turn every 6 s of narration, each one shot


# ---- the server: the real app with fake Meta adapters ----


def serve(port: int, data: Path, scale: float, admin_token: str) -> None:
    import uvicorn
    from PIL import Image

    from frameteller.application.ports import (
        DirectedTurn,
        EditIntent,
        EditRequest,
        ImageRequest,
        PartialTranscript,
        ReviewRequest,
        Segment,
        ShotDraft,
        SpeechEvent,
        SpeechOptions,
        StoredImage,
        TurnCompleted,
        TurnEnded,
        TurnStarted,
    )
    from frameteller.domain import Character, Framing, MediaRef, Point, Project, Shot, Size, TranscriptTurn
    from frameteller.domain.review import Decision, Verdict
    from frameteller.infrastructure.config import Settings
    from frameteller.infrastructure.local import (
        FileShareIndex,
        FileSpendLedger,
        FileVisitorQuota,
        JsonFileProjectRepository,
        LocalFileMediaStorage,
    )
    from frameteller.infrastructure.review import FileRubricLibrary
    from frameteller.interface.app import create_app
    from frameteller.interface.container import wire

    async def pause(kind: str) -> None:
        await asyncio.sleep(LATENCY[kind] / scale)

    def webp(shade: int) -> bytes:
        out = io.BytesIO()
        Image.new("RGB", (1920, 1280), (40 + shade * 20, 60, 120 - shade * 10)).save(out, "WEBP", quality=80)
        return out.getvalue()

    frames = [webp(i) for i in range(6)]
    cast = (
        Character("mira", "Mira", "a tall woman in a yellow raincoat with short silver hair"),
        Character("pip", "Pip", "a small grey cat with one white ear and a glowing collar"),
    )
    sentences = (
        "Night falls over a rainy alley and Mira walks home under a flickering sign.",
        "Something glows behind the bins and she crouches to look closer.",
        "A small grey cat named Pip blinks up at her, its collar shining.",
        "Mira lifts Pip into her coat and the rain seems to stop for a moment.",
        "They climb the fire escape together towards the bright rooftop.",
        "On the roof the whole city hums and Pip purrs like a little engine.",
    )

    class Speech:
        async def stream(self, audio: AsyncIterator[bytes], options: SpeechOptions) -> AsyncIterator[SpeechEvent]:
            received, n = 0, 0
            async for chunk in audio:
                received += len(chunk)
                if received // BYTES_PER_MS >= (n + 1) * TURN_EVERY_MS:
                    start, end = n * TURN_EVERY_MS, (n + 1) * TURN_EVERY_MS - 400
                    text = sentences[n % len(sentences)]
                    yield TurnStarted(str(n), start)
                    yield PartialTranscript(text)
                    yield TurnEnded(str(n), end)
                    yield TurnCompleted(TranscriptTurn(str(n), text, start, end))
                    n += 1

        async def transcribe_file(self, wav: bytes, options: SpeechOptions) -> list[TranscriptTurn]:
            return []

    class Director:
        async def direct_turn(self, turn: TranscriptTurn, project: Project) -> DirectedTurn:
            await pause("turn")
            known = set(project.bible.characters)
            new = tuple(c for c in cast if c.id not in known)
            framing = (Framing.WIDE, Framing.MEDIUM, Framing.CLOSE_UP)[len(project.shots) % 3]
            draft = ShotDraft(
                framing,
                ("mira", "pip"),
                "a rainy alley at night",
                turn.text,
                "",
                (turn.id,),
                turn.end_ms - turn.start_ms,
            )
            return DirectedTurn(new, (draft,))

        async def direct_story(self, project: Project) -> DirectedTurn:
            return DirectedTurn((), ())

        async def extract_characters(
            self, turns: Sequence[TranscriptTurn], known: Sequence[Character]
        ) -> list[Character]:
            await pause("cast")
            return list(known) or list(cast)

        async def interpret_edit(self, instruction: str, shot: Shot, cast: Sequence[Character]) -> EditIntent:
            await pause("turn")
            return EditIntent("cat", ("fur",), instruction)

        async def translate(self, texts: Sequence[str], language: str) -> list[str]:
            await pause("turn")
            return list(texts)

    class Images:
        def __init__(self, storage: LocalFileMediaStorage) -> None:
            self.storage, self.n = storage, 0

        async def generate(self, request: ImageRequest, store_as: str) -> StoredImage:
            await pause("image")
            return await self._store(store_as)

        async def edit(self, request: EditRequest, store_as: str) -> StoredImage:
            await pause("edit")
            return await self._store(store_as)

        async def _store(self, key: str) -> StoredImage:
            self.n += 1
            ref = await self.storage.put(key, frames[self.n % len(frames)], "image/webp")
            return StoredImage(ref, f"resp_{self.n}", Size(1920, 1280))

    class Sam:
        async def segment_concept(self, image: MediaRef, concept: str, store_prefix: str) -> list[Segment]:
            await pause("sam")
            return []

        async def segment_point(self, image: MediaRef, point: Point, store_prefix: str) -> Segment | None:
            await pause("sam")
            return None

    class Reviewer:
        async def review(self, request: ReviewRequest) -> Verdict:
            await pause("review")
            return Verdict(Decision.PASS, 0.9, (), "", "", (), "fake-reviewer", 0, ())

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        model_api_key="fake-load-test",
        app_env="local",
        storage_backend="local",
        local_storage_dir=data,
        admin_token=admin_token,
        rate_limit_per_minute=100_000,
        rate_limit_costly_per_minute=100_000,
        log_level="WARNING",
    )
    storage = LocalFileMediaStorage(data)
    director = Director()
    container = wire(
        settings,
        repo=JsonFileProjectRepository(data),
        storage=storage,
        director=director,
        translator=director,
        images=Images(storage),
        segmentation=Sam(),
        speech=Speech(),
        reviewer=Reviewer(),
        rubrics=FileRubricLibrary(settings.rubrics_path),
        ledger=FileSpendLedger(data),
        shares=FileShareIndex(data),
        quota=FileVisitorQuota(data),
    )
    uvicorn.run(create_app(container=container), host="127.0.0.1", port=port, log_level="warning", ws_max_size=2**24)


# ---- the visitors ----


def rest(base: str, method: str, path: str, visitor: str, body: Any = None, token: str = "") -> tuple[int, Any]:
    headers = {"Content-Type": "application/json", "X-Visitor-Id": visitor}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:200]
    except urllib.error.URLError as e:
        return 0, str(e.reason)


class Visitor:
    def __init__(self, n: int, base: str, narration_s: float) -> None:
        self.n, self.base, self.narration_s = n, base, narration_s
        self.id = f"load-{n:03d}-{secrets.token_hex(4)}"
        self.events: list[dict[str, Any]] = []
        self.changed = asyncio.Event()
        self.times: dict[str, float] = {}
        self.waited_place = 0
        self.error = ""

    async def call(self, method: str, path: str, body: Any = None, label: str = "") -> tuple[int, Any]:
        t = time.perf_counter()
        status, data = await asyncio.to_thread(rest, self.base, method, path, self.id, body)
        self.times.setdefault(f"http {method} {label or path.split('/')[-1]}", time.perf_counter() - t)
        return status, data

    async def listen(self, ws: Any) -> None:
        async for raw in ws:
            event = json.loads(raw)
            self.events.append(event)
            if event["type"] == "queue.waiting":
                self.waited_place = max(self.waited_place, event["position"])
            self.changed.set()

    async def until(self, done: Any, timeout: float) -> None:
        async with asyncio.timeout(timeout):
            while not done():
                self.changed.clear()
                await self.changed.wait()

    def finished(self, kind: str, keys: set[str]) -> bool:
        ended = {
            e["key"]
            for e in self.events
            if e["type"] == "job.updated" and e["kind"] == kind and e["status"] in ("succeeded", "failed")
        }
        return keys <= ended

    def failed(self, kind: str) -> list[str]:
        return [
            e.get("message") or ""
            for e in self.events
            if e["type"] == "job.updated" and e["kind"] == kind and e["status"] == "failed"
        ]

    async def run(self, timeout: float) -> None:
        import websockets

        t0 = time.perf_counter()
        status, project = await self.call("POST", "/projects", {"title": f"Load visitor {self.n}"})
        if status != 201:
            self.error = f"create {status} {project}"
            return
        pid = project["id"]
        url = self.base.replace("http", "ws", 1) + f"/ws/projects/{pid}/session"
        async with websockets.connect(url, max_size=None, additional_headers={"X-Visitor-Id": self.id}) as ws:
            listener = asyncio.create_task(self.listen(ws))
            try:
                await ws.send(json.dumps({"mode": "narrate", "keywords": ["Mira", "Pip"]}))
                t = time.perf_counter()
                await self.until(lambda: any(e["type"] == "session.started" for e in self.events), timeout)
                self.times["seat (waiting room)"] = time.perf_counter() - t

                pcm = bytes(int(self.narration_s * 1000) * BYTES_PER_MS)
                step, started = FRAME_MS * BYTES_PER_MS, time.perf_counter()
                for i, offset in enumerate(range(0, len(pcm), step)):
                    await asyncio.sleep(max(0.0, started + i * FRAME_MS / 1000 - time.perf_counter()))
                    if offset and (offset // BYTES_PER_MS) % TURN_EVERY_MS == 0:
                        await ws.send(json.dumps({"type": "beat"}))
                    await ws.send(pcm[offset : offset + step])
                await ws.send(json.dumps({"type": "end"}))
                t = time.perf_counter()
                await self.until(lambda: any(e["type"] == "session.ended" for e in self.events), timeout)
                self.times["end -> session.ended"] = time.perf_counter() - t
                cast = {e["key"] for e in self.events if e["type"] == "job.updated" and e["kind"] == "generate_cast"}
                await self.until(lambda: self.finished("generate_cast", cast), timeout)
                self.times["end -> cast sheets drawn"] = time.perf_counter() - t

                status, review = await self.call("POST", f"/projects/{pid}/cast/approve", {})
                if status != 200 or not review.get("approved"):
                    self.error = f"approve {status} {review} {self.failed('generate_cast')}"
                    return
                _, project = await self.call("GET", f"/projects/{pid}", label="project")
                t, keys = time.perf_counter(), set()
                for shot in project["shots"]:
                    status, ticket = await self.call(
                        "POST", f"/projects/{pid}/shots/{shot['number']}/panel", {"quality": "draft"}
                    )
                    if status != 202:
                        self.error = f"panel {status} {ticket}"
                        return
                    keys.add(ticket["key"])
                await self.until(lambda: self.finished("generate_panel", keys), timeout)
                self.times[f"draw {len(keys)} draft panels"] = time.perf_counter() - t
                if self.failed("generate_panel"):
                    self.error = f"panels failed {self.failed('generate_panel')[:2]}"
                    return

                t = time.perf_counter()
                status, ticket = await self.call("POST", f"/projects/{pid}/exports/animatic", {"subtitles": True})
                if status != 202:
                    self.error = f"export {status} {ticket}"
                    return
                await self.until(lambda: self.finished("export_animatic", {ticket["key"]}), timeout)
                self.times["export animatic"] = time.perf_counter() - t
                if self.failed("export_animatic"):
                    self.error = f"export failed {self.failed('export_animatic')}"
                    return
                self.times["whole visit"] = time.perf_counter() - t0
            except TimeoutError:
                self.error = f"timed out after {sorted(self.times)[-1:] or 'start'}"
            finally:
                listener.cancel()
                await asyncio.gather(listener, return_exceptions=True)


# ---- measuring the server ----


def tree(pid: int) -> tuple[float, int]:
    """CPU seconds (the process, its reaped and live children) and resident bytes of the process tree."""
    cpu, rss = 0.0, 0
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            stat = Path(f"/proc/{entry}/stat").read_text()
        except OSError:
            continue
        fields = stat[stat.rindex(")") + 2 :].split()
        ppid, utime, stime, cutime, cstime, pages = int(fields[1]), *map(int, fields[11:15]), int(fields[21])
        if int(entry) == pid:
            cpu += (utime + stime + cutime + cstime) / TICK
            rss += pages * PAGE
        elif ppid == pid:
            cpu += (utime + stime) / TICK
            rss += pages * PAGE
    return cpu, rss


async def sample(pid: int, base: str, token: str, out: dict[str, Any], stop: asyncio.Event) -> None:
    last_cpu, last_t = tree(pid)[0], time.perf_counter()
    while not stop.is_set():
        await asyncio.sleep(1)
        cpu, rss = tree(pid)
        now = time.perf_counter()
        out["cpu"].append((cpu - last_cpu) / (now - last_t) * 100)
        out["rss"].append(rss)
        last_cpu, last_t = cpu, now
        status, overview = await asyncio.to_thread(rest, base, "GET", "/admin/overview", "sampler", None, token)
        if status == 200:
            for gate in overview["gates"]:
                out["waiting"][gate["name"]] = max(out["waiting"][gate["name"]], gate["waiting"])
                out["in_flight"][gate["name"]] = max(out["in_flight"][gate["name"]], gate["in_flight"])
            out["live"] = max(out["live"], overview["live_sessions"])
            out["spent"] = overview["budgets"][0]["spent_usd"] if overview["budgets"] else 0


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)]


async def drive(args: argparse.Namespace, pid: int, token: str) -> int:
    base = f"http://127.0.0.1:{args.port}"
    async with asyncio.timeout(30):
        while (await asyncio.to_thread(rest, base, "GET", "/healthz", "probe"))[0] != 200:
            await asyncio.sleep(0.3)
    idle_rss = tree(pid)[1]
    stats: dict[str, Any] = {
        "cpu": [],
        "rss": [],
        "waiting": defaultdict(int),
        "in_flight": defaultdict(int),
        "live": 0,
    }
    stop = asyncio.Event()
    sampler = asyncio.create_task(sample(pid, base, token, stats, stop))
    visitors = [Visitor(n, base, args.narration) for n in range(args.visitors)]

    async def arrive(v: Visitor) -> None:
        await asyncio.sleep(args.ramp * v.n / max(1, args.visitors - 1))
        await v.run(args.timeout)

    t0 = time.perf_counter()
    await asyncio.gather(*(arrive(v) for v in visitors))
    wall = time.perf_counter() - t0
    stop.set()
    await sampler

    ok = [v for v in visitors if not v.error]
    seated_later = sum(v.waited_place > 0 for v in visitors)
    print(
        f"\n{args.visitors} visitors over {args.ramp:.0f} s, {args.narration:.0f} s narration, latency / {args.scale}"
    )
    print(f"finished {len(ok)}/{len(visitors)} in {wall:.0f} s; waited for a seat: {seated_later}")
    for v in visitors:
        if v.error:
            print(f"  visitor {v.n}: {v.error}")
    steps = sorted({k for v in ok for k in v.times}, key=lambda k: min(v.times.get(k, 1e9) for v in ok))
    print(f"\n{'step':<36} {'p50':>7} {'p95':>7} {'max':>7}  (seconds)")
    for step in steps:
        values = [v.times[step] for v in ok if step in v.times]
        print(f"{step:<36} {statistics.median(values):7.2f} {pct(values, 0.95):7.2f} {max(values):7.2f}")
    print("\nlongest line per gate (in flight at most)")
    for name in sorted(stats["in_flight"]):
        print(f"  {name:<9} waiting {stats['waiting'][name]:>3}   in flight {stats['in_flight'][name]:>3}")
    print(f"  live sessions at most: {stats['live']}; budget charged (estimates): ${stats.get('spent', 0):.2f}")
    cpu, rss = stats["cpu"], stats["rss"]
    mean, p95 = statistics.fmean(cpu), pct(cpu, 0.95)
    print(f"\nserver CPU: mean {mean:.0f}%  p95 {p95:.0f}%  max {max(cpu):.0f}%  (100% = one core)")
    print(f"server memory: idle {idle_rss / 2**20:.0f} MiB, peak {max(rss) / 2**20:.0f} MiB (process + ffmpeg)")
    return 0 if len(ok) == len(visitors) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--visitors", type=int, default=50)
    parser.add_argument("--ramp", type=float, default=60, help="seconds over which visitors arrive")
    parser.add_argument("--narration", type=float, default=24, help="seconds of narration per visitor")
    parser.add_argument("--scale", type=float, default=1.0, help="divide the fake model latencies by this")
    parser.add_argument("--timeout", type=float, default=1800, help="per step, seconds")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--serve", type=Path, help=argparse.SUPPRESS)  # the server subprocess: its data dir
    args = parser.parse_args()
    if args.serve:
        serve(args.port, args.serve, args.scale, os.environ["LOAD_TEST_ADMIN_TOKEN"])
        return 0
    token = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix="frameteller-load-") as data:
        server = subprocess.Popen(
            [sys.executable, __file__, "--serve", data, "--port", str(args.port), "--scale", str(args.scale)],
            env={**os.environ, "LOAD_TEST_ADMIN_TOKEN": token},
        )
        try:
            return asyncio.run(drive(args, server.pid, token))
        finally:
            server.terminate()  # queued jobs of finished visits may still be running: they are dropped
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    sys.exit(main())
