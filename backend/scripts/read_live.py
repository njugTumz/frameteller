""" "Read it to me" live check (ADR 0015): a voice reads a script, the storyboard is drawn, and the animatic exported.

    cd backend && .venv/bin/python scripts/read_live.py --api https://<staging> --script rooftop.txt --language fr-FR

Creates a project and starts a read session with the voice and language, plays nothing but keeps pace like a
browser would: it continues after an episode break as soon as asked to, approves the proposed cast and draws a
draft per shot. With --export it then exports the animatic and checks it is voiced by the synthesized narration.
Prints per paragraph when its audio arrived, its length and the spoken text. Spends Azure Text-to-Speech
characters (USD 15 per million) and Meta credits for the director, translation, sheets and drafts.
Never reads .env: the server holds every key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import websockets

T0 = time.perf_counter()
# Counted as its own browser for the per-visitor demo limits (the studio sends one per browser too).
VISITOR = "read-check-0001"


def now() -> float:
    return time.perf_counter() - T0


def rest(api: str, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    req = urllib.request.Request(
        api + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Visitor-Id": VISITOR},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read() or b"null")


async def drafts(api: str, project: str, timeout_s: float = 600) -> dict[str, Any]:
    """Approve the cast once its sheets and outfit sheets are in, draw a draft per shot, wait for every panel."""
    asked: set[int] = set()
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        p = rest(api, "GET", f"/projects/{project}")
        if (
            p["cast"]["status"] != "approved"
            and p["cast"]["characters"]
            and all(c["reference_url"] for c in p["cast"]["characters"])
            and all(look["reference_url"] for c in p["cast"]["characters"] for look in c.get("looks", []))
        ):
            rest(api, "POST", f"/projects/{project}/cast/approve", {})
            continue
        if p["cast"]["status"] == "approved":
            for s in p["shots"]:
                if s["number"] not in asked and not s["panel"]:
                    rest(api, "POST", f"/projects/{project}/shots/{s['number']}/panel", {"quality": "draft"})
                    asked.add(s["number"])
            if p["shots"] and all(s["panel"] and s["panel"]["status"] in ("ready", "failed") for s in p["shots"]):
                return dict(p)
        await asyncio.sleep(3)
    raise TimeoutError("the drafts did not finish")


async def read(api: str, project: str, script: str, voice: str, language: str) -> list[tuple[float, dict[str, Any]]]:
    events: list[tuple[float, dict[str, Any]]] = []
    url = api.replace("https://", "wss://").replace("http://", "ws://") + f"/ws/projects/{project}/session"
    async with websockets.connect(url, max_size=None) as ws:
        await ws.send(json.dumps({"mode": "read", "script": script, "voice": voice, "language": language}))
        drawing: asyncio.Task[dict[str, Any]] | None = None
        async for raw in ws:
            e = json.loads(raw)
            events.append((now(), e))
            if e["type"] == "script.voiced":
                print(
                    f"[{now():6.1f}s] voiced {e['paragraph']} ({e['duration_ms'] / 1000:.1f} s): {e['text'][:70]}",
                    flush=True,
                )
            elif e["type"] in ("script.paused", "script.resumed", "error", "session.started"):
                print(f"[{now():6.1f}s] {e}", flush=True)
            if e["type"] == "cast.proposed" and drawing is None:
                drawing = asyncio.create_task(drafts(api, project))  # as the studio does while the voice reads
            if e["type"] == "session.ended":
                print(f"[{now():6.1f}s] ended: {e}", flush=True)
                break
        if drawing is None:
            drawing = asyncio.create_task(drafts(api, project))
        await drawing
    return events


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--voice", default="en-US-AvaMultilingualNeural")
    parser.add_argument("--language", default="en-US")
    parser.add_argument("--title", default="Read it to me check")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    api = args.api.rstrip("/")
    voices = rest(api, "GET", "/voices")
    print("voices:", [(v["display_name"], [x["code"] for x in v["languages"]]) for v in voices["voices"]])
    if not voices["available"]:
        raise SystemExit("Read it to me is not available on this backend (no AZURE_SPEECH_KEY).")
    project = rest(api, "POST", "/projects", {"title": args.title, "style": "pencil"})["id"]
    print("project", project)
    events = await read(api, project, args.script.read_text(), args.voice, args.language)
    voiced = [e for _, e in events if e["type"] == "script.voiced"]
    first = next(t for t, e in events if e["type"] == "script.voiced")
    total = sum(v["duration_ms"] for v in voiced) / 1000
    print(f"first audio after {first:.1f} s; {len(voiced)} paragraphs, {total:.1f} s of narration")
    p = rest(api, "GET", f"/projects/{project}")
    drawn = sum(1 for s in p["shots"] if s["panel"] and s["panel"]["status"] == "ready")
    print(f"[{now():6.1f}s] {len(p['shots'])} shots, {drawn} drafts ready; narrations {p['narrations']}")
    if args.export:
        rest(api, "POST", f"/projects/{project}/exports/animatic", {"subtitles": False})
        for _ in range(120):
            p = rest(api, "GET", f"/projects/{project}")
            if p["animatic"]:
                break
            await asyncio.sleep(3)
        print(f"[{now():6.1f}s] animatic {p['animatic']}")
        share = rest(api, "POST", f"/projects/{project}/share", {"public": False})
        page = rest(api, "GET", f"/shares/{share['token']}")
        print(f"share page: narrated_by={page['narrated_by']!r}, animatic={page['animatic']}")


if __name__ == "__main__":
    asyncio.run(main())
