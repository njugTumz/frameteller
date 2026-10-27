"""Spike 1: voice -> transcript turns -> structured shot list.

With spikes/fixtures/narration.wav (mono 24 kHz s16le) it streams the audio to
realtime ASR and also sends it to the file endpoint. Without it, it builds
synthetic turns from story.txt at 150 words per minute.

Usage: spikes/.venv/bin/python spikes/s1_voice_to_shots.py
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
import uuid
import wave
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ValidationError

from common import (
    ASR_MODEL,
    BASE_URL,
    FIXTURES,
    OUT,
    PRICE_ASR_PER_HOUR,
    TEXT_MODEL,
    api_key,
    client,
    log_cost,
    reserve,
    spark_cost,
    timed,
    usage_of,
    write_json,
)

SPIKE = "s1"
WAV = FIXTURES / "narration.wav"
STORY = FIXTURES / "story.txt"
WPM = 150
FRAME_MS = 80
BYTES_PER_MS = 48  # PCM_24KHZ s16le mono = 48,000 bytes/s


# ---------- Audio paths (only when narration.wav exists) ----------

def check_wav(path: Path) -> float:
    with wave.open(str(path)) as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, 24000):
            raise SystemExit("narration.wav must be mono, 16-bit, 24 kHz")
        return w.getnframes() / 24000


def pcm_bytes(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        return w.readframes(w.getnframes())


async def realtime_turns(path: Path) -> list[dict]:
    import websockets

    pcm = pcm_bytes(path)
    turns: dict[str, dict] = {}
    order: list[str] = []
    current: str | None = None
    partial = ""
    end_wall: dict[str, float] = {}

    async with websockets.connect(BASE_URL.replace("https", "wss") + "/asr/realtime", max_size=None) as ws:
        # Auth goes in the first frame; the HTTP Authorization header is ignored.
        await asyncio.wait_for(ws.send(json.dumps({
            "model": ASR_MODEL,
            "authorization": {"accessToken": f"Bearer {api_key()}"},
            "audioEncoding": "PCM_24KHZ",
            "mode": "ENDPOINTING",
            "partialMode": "CUMULATIVE",
            "keywords": ["Mira"],
        })), timeout=10)
        while True:
            ack = json.loads(await ws.recv())
            if "sessionId" in ack:
                break

        async def send_audio() -> None:
            step = FRAME_MS * BYTES_PER_MS
            t0 = time.perf_counter()
            for i, off in enumerate(range(0, len(pcm), step)):
                # Pace at real time: the server rejects streams that run ahead.
                await asyncio.sleep(max(0.0, t0 + i * FRAME_MS / 1000 - time.perf_counter()))
                await ws.send(pcm[off:off + step])
            await ws.send(json.dumps({"type": "endStream"}))

        sender = asyncio.create_task(send_audio())
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                ev = json.loads(raw)
                kind = ev.get("type")
                tid = ev.get("turnId")
                if kind == "speechStart":
                    current, partial = tid, ""
                    turns[tid] = {"turnId": tid, "start_ms": ev.get("audioProcessedMs"), "end_ms": None, "text": None}
                    order.append(tid)
                elif kind == "transcript":
                    partial = ev.get("transcript", partial)  # cumulative: replace, never append
                    if current in turns:
                        turns[current]["partial"] = partial
                elif kind == "speechEnd" and tid in turns:
                    turns[tid]["end_ms"] = ev.get("audioProcessedMs")
                    end_wall[tid] = time.perf_counter()
                elif kind == "speechComplete" and tid in turns:
                    turns[tid]["text"] = ev.get("transcript")
                    if tid in end_wall:
                        turns[tid]["final_latency_ms"] = round((time.perf_counter() - end_wall[tid]) * 1000)
                # Unknown event types are ignored on purpose.
        finally:
            await sender
        if ws.close_code != 1000:
            raise RuntimeError(f"realtime ASR closed with {ws.close_code}")

    return [{**turns[t], "duration_ms": (turns[t]["end_ms"] or 0) - (turns[t]["start_ms"] or 0)} for t in order]


def file_turns(path: Path) -> list[dict]:
    request = {"model": ASR_MODEL, "mode": "ENDPOINTING", "keywords": ["Mira"]}
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"request\"\r\n"
        f"Content-Type: application/json\r\n\r\n{json.dumps(request)}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"{path.name}\"\r\n"
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE_URL}/asr/transcribe", data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(2 ** attempt)
    return [
        {"turnId": t["turnId"], "start_ms": t["startMs"], "end_ms": t["endMs"],
         "duration_ms": t["endMs"] - t["startMs"], "text": t["transcript"], "speaker": t.get("speaker")}
        for t in data.get("turns", [])
    ]


def synthetic_turns() -> list[dict]:
    turns, t = [], 0
    for i, line in enumerate(l.strip() for l in STORY.read_text().splitlines() if l.strip()):
        dur = round(len(line.split()) / WPM * 60_000)
        turns.append({"turnId": f"syn-{i + 1}", "start_ms": t, "end_ms": t + dur, "duration_ms": dur, "text": line})
        t += dur
    return turns


# ---------- Director (Spark, structured output) ----------

class Framing(str, Enum):
    wide = "wide"
    medium = "medium"
    close_up = "close_up"
    over_shoulder = "over_shoulder"
    insert = "insert"


class Character(BaseModel):
    id: str
    name: str
    canonical_description: str


class Shot(BaseModel):
    shot_number: int
    framing: Framing
    character_ids: list[str]
    setting: str
    action: str
    dialogue: str
    source_turn_ids: list[str]
    duration_ms: int


class Storyboard(BaseModel):
    title: str
    characters: list[Character]
    shots: list[Shot]


# Stable prefix: identical bytes on every call so prompt caching can hit.
SYSTEM_PROMPT = """You are the director's assistant in Frameteller, a tool that turns a spoken story into a storyboard.

You receive transcript turns as JSON. Each turn has a turnId, start_ms, end_ms, duration_ms and text.
Return a Storyboard:
- title: a short title for the scene.
- characters: every character who appears, including animals. id is a short lowercase slug (e.g. "mira").
  canonical_description is ONE stable visual description used to draw the character in every panel:
  age, build, face, hair, clothing with colours, and any distinctive features. Be specific and concrete,
  never mention camera framing or actions. Invent nothing that contradicts the transcript.
- shots: one or more shots per turn, in story order, numbered from 1.
  framing is one of wide, medium, close_up, over_shoulder, insert. Honour explicit cues like "wide shot" or "close on".
  character_ids lists only ids from characters that are visible in the shot.
  setting is where and when, action is what we see, dialogue is spoken words or "" if none.
  source_turn_ids lists the turnIds the shot comes from.
  duration_ms is the sum of duration_ms of the source turns; if one turn yields several shots, split its duration between them.
Keep the story original. Do not add real people, brands or copyrighted characters."""


def check_storyboard(sb: Storyboard, turns: list[dict]) -> list[str]:
    ids = {c.id for c in sb.characters}
    turn_ids = {t["turnId"] for t in turns}
    errors = []
    for s in sb.shots:
        if unknown := set(s.character_ids) - ids:
            errors.append(f"shot {s.shot_number}: unknown character_ids {sorted(unknown)}")
        if not s.source_turn_ids or set(s.source_turn_ids) - turn_ids:
            errors.append(f"shot {s.shot_number}: bad source_turn_ids {s.source_turn_ids}")
    if [s.shot_number for s in sb.shots] != list(range(1, len(sb.shots) + 1)):
        errors.append("shot numbers are not contiguous from 1")
    return errors


def direct(turns: list[dict], label: str) -> tuple[Storyboard, dict]:
    oai = client()
    user = "Transcript turns:\n" + json.dumps(turns, ensure_ascii=False)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
    for attempt in (1, 2):  # retry once with the validation error
        reserve(0.01)
        with timed() as t:
            resp = oai.responses.parse(model=TEXT_MODEL, input=messages, text_format=Storyboard)
        i, o, c = usage_of(resp)
        log_cost(spike=SPIKE, model=TEXT_MODEL, latency_s=t.seconds, cost_usd=spark_cost(i, o, c),
                 input_tokens=i, output_tokens=o, cached_tokens=c, note=f"director {label} attempt {attempt}")
        try:
            sb = resp.output_parsed
            if sb is None:
                raise ValueError("no parsed output")
            errors = check_storyboard(sb, turns)
            if not errors:
                return sb, {"latency_s": round(t.seconds, 2), "input_tokens": i, "output_tokens": o,
                            "cached_tokens": c, "attempts": attempt}
            raise ValueError("; ".join(errors))
        except (ValidationError, ValueError) as e:
            if attempt == 2:
                raise
            messages += [{"role": "assistant", "content": resp.output_text},
                         {"role": "user", "content": f"That output failed validation: {e}. Return a corrected Storyboard."}]
    raise AssertionError("unreachable")


def main() -> None:
    findings: dict = {}
    if WAV.exists():
        seconds = check_wav(WAV)
        reserve(PRICE_ASR_PER_HOUR * seconds / 3600 * 2)
        with timed() as t:
            turns = asyncio.run(realtime_turns(WAV))
        log_cost(spike=SPIKE, model=ASR_MODEL, latency_s=t.seconds,
                 cost_usd=PRICE_ASR_PER_HOUR * int(seconds + 0.999) / 3600, note="realtime")
        write_json(OUT / "s1_turns.json", {"source": "realtime", "turns": turns})
        with timed() as t:
            ft = file_turns(WAV)
        log_cost(spike=SPIKE, model=ASR_MODEL, latency_s=t.seconds,
                 cost_usd=PRICE_ASR_PER_HOUR * int(seconds + 0.999) / 3600, note="file")
        write_json(OUT / "s1_turns_file.json", {"source": "file", "turns": ft})
        findings["asr"] = {
            "realtime_turns": len(turns), "file_turns": len(ft),
            "final_latency_ms": [x.get("final_latency_ms") for x in turns],
            "boundaries_realtime": [(x["start_ms"], x["end_ms"]) for x in turns],
            "boundaries_file": [(x["start_ms"], x["end_ms"]) for x in ft],
        }
    else:
        turns = synthetic_turns()
        write_json(OUT / "s1_turns.json", {
            "source": "SYNTHETIC: built from story.txt at 150 wpm; narration.wav not provided, voice test pending",
            "turns": turns,
        })
        findings["asr"] = "skipped: no narration.wav, synthetic turns used"

    sb1, run1 = direct(turns, "run 1")
    sb2, run2 = direct(turns, "run 2")

    # duration_ms must come from turn timings; compare the model's numbers with ours.
    by_id = {t["turnId"]: t for t in turns}
    duration_check = []
    for s in sb1.shots:
        share = sum(by_id[tid]["duration_ms"] / max(1, sum(tid in x.source_turn_ids for x in sb1.shots))
                    for tid in s.source_turn_ids)
        duration_check.append({"shot": s.shot_number, "model_ms": s.duration_ms, "from_turns_ms": round(share)})

    write_json(OUT / "s1_storyboard.json", {
        "storyboard": sb1.model_dump(mode="json"),
        "turns_source": "synthetic" if not WAV.exists() else "realtime",
        "director_runs": [run1, run2],
        "duration_check": duration_check,
        "run2_same_shot_count": len(sb2.shots) == len(sb1.shots),
        "findings": findings,
    })
    print(json.dumps({"runs": [run1, run2], "shots": len(sb1.shots),
                      "characters": [c.id for c in sb1.characters], "duration_check": duration_check}, indent=2))


if __name__ == "__main__":
    main()
