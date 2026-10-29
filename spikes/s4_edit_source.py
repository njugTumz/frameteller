"""Spike 4: how long does a Muse Image edit chain live, and is an edit from our stored image as faithful?

Production lost a chain about two minutes after the panel was drawn (400 "referenced response not found or
expired"). This spike measures, on a lighthouse panel (Ada, pencil, synthetic story):

1. Chaining from a panel drawn about an hour ago.
2. An edit from the stored image (no chain): the panel and Ada's sheet as input_image parts.
3. The same change chained and from the stored image, from the same fresh source, compared by how much of the
   panel outside Ada changes structurally (6 px blur, the method of spike 3).
4. Chaining from that fresh source after 3, 6 and 12 minutes.

About 7 images, USD 0.07. Output: spikes/out/s4/ (gitignored).

    spikes/.venv/bin/python spikes/s4_edit_source.py
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from common import (
    OUT,
    PRICE_IMAGE,
    async_client,
    image_from_response,
    image_tool,
    log_cost,
    reserve,
    timed,
    write_json,
)

STORE = OUT / "lighthouse-supervised" / "store"
PROJECT = "69c38746c30f40d98a43a3ca4862dcde"
SHOT_NUMBER = 2  # Ada polishes the lamp: Ada alone, medium shot
S4 = OUT / "s4"
SIZE = "1536x1024"

RED = (
    "Change the old woman's green sweater to red, including its sleeves and collar. "
    "Keep everything else identical."
)
BLUE = (
    "Change the old woman's sweater to blue, including its sleeves and collar. "
    "Keep everything else identical."
)
STORED = (
    "Edit the first image. {change} Keep the composition, framing, pose, lighting, line work and style of the "
    "first image exactly. The second image is the character's reference sheet: keep her face, hair and build "
    "as it shows."
)


def project() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((STORE / "projects" / f"{PROJECT}.json").read_text())
    return data


def media(key: str) -> Path:
    return STORE / "media" / key


def data_url(raw: bytes) -> str:
    import base64

    fmt = (Image.open(io.BytesIO(raw)).format or "PNG").lower()
    return f"data:image/{fmt};base64," + base64.b64encode(raw).decode()


def structural(before: bytes, after: bytes, box: list[int]) -> dict[str, float]:
    """Share of pixels that change after a 6 px blur, outside and inside the character's box (grown 24 px)."""
    a = Image.open(io.BytesIO(before)).convert("RGB")
    b = Image.open(io.BytesIO(after)).convert("RGB").resize(a.size)
    blur = ImageFilter.GaussianBlur(6)
    diff = np.abs(np.asarray(a.filter(blur), np.int16) - np.asarray(b.filter(blur), np.int16)).max(axis=2) > 24
    raw = np.abs(np.asarray(a, np.int16) - np.asarray(b, np.int16)).max(axis=2) > 24
    inside = np.zeros(diff.shape, bool)
    left, top, right, bottom = box
    g = 24
    inside[max(0, top - g) : bottom + g, max(0, left - g) : right + g] = True
    return {
        "structural_outside_pct": round(100 * float(diff[~inside].mean()), 2),
        "structural_inside_pct": round(100 * float(diff[inside].mean()), 2),
        "raw_outside_pct": round(100 * float(raw[~inside].mean()), 2),
    }


async def render(note: str, **kwargs: Any) -> tuple[bytes | None, str | None, float, str]:
    reserve(PRICE_IMAGE)
    client = async_client()
    with timed() as t:
        try:
            response = await client.responses.create(model="muse-image-1.0", **kwargs)
        except Exception as e:  # noqa: BLE001 - the error text is the finding
            log_cost(spike="s4", model="muse-image-1.0", latency_s=t.seconds, cost_usd=0.0, note=f"{note}: failed")
            return None, None, t.seconds, str(e)[:200]
    raw = image_from_response(response)
    log_cost(spike="s4", model="muse-image-1.0", latency_s=t.seconds, cost_usd=PRICE_IMAGE, note=note)
    return raw, response.id, t.seconds, "ok"


async def chained(response_id: str, change: str, note: str) -> tuple[bytes | None, str | None, float, str]:
    return await render(
        note, previous_response_id=response_id, input=change, tools=[image_tool(SIZE, "low")]
    )


async def from_stored(panel: bytes, sheet: bytes, change: str, note: str) -> tuple[bytes | None, str | None, float, str]:
    content = [
        {"type": "input_text", "text": STORED.format(change=change)},
        {"type": "input_image", "image_url": data_url(panel)},
        {"type": "input_image", "image_url": data_url(sheet)},
    ]
    return await render(note, input=[{"role": "user", "content": content}], tools=[image_tool(SIZE, "low")])


async def main() -> None:
    S4.mkdir(parents=True, exist_ok=True)
    p = project()
    shot = next(s for s in p["shots"] if s["number"] == SHOT_NUMBER)
    panel = next(x for x in p["panels"] if x["shot_id"] == shot["id"])
    ada = next(m for m in panel["masks"] if m.get("character_id") == "ada")
    panel_path = media(panel["image"])
    panel_bytes = panel_path.read_bytes()
    sheet = media(next(c for c in p["characters"] if c["id"] == "ada")["reference"]).read_bytes()
    results: dict[str, Any] = {"panel_drawn_at": time.strftime("%H:%M:%S", time.localtime(panel_path.stat().st_mtime))}

    def keep(name: str, raw: bytes | None) -> None:
        if raw:
            (S4 / f"{name}.webp").write_bytes(raw)

    age_min = round((time.time() - panel_path.stat().st_mtime) / 60, 1)
    raw, _, s, status = await chained(panel["response_id"], RED, f"chain from a panel {age_min} min old")
    results["old_chain"] = {"age_min": age_min, "status": status, "latency_s": round(s, 1)}
    keep("old-chain-red", raw)
    print("old chain", results["old_chain"], flush=True)

    fresh, fresh_id, s, status = await from_stored(panel_bytes, sheet, RED, "stored-image edit: red")
    assert fresh and fresh_id, status
    born = time.time()
    keep("stored-red", fresh)
    results["stored_red"] = {"latency_s": round(s, 1), **structural(panel_bytes, fresh, ada["box"])}
    print("stored red", results["stored_red"], flush=True)

    raw, _, s, status = await chained(fresh_id, BLUE, "chain at once: blue")
    keep("chain-blue", raw)
    results["chain_blue"] = {"status": status, "latency_s": round(s, 1)}
    if raw:
        results["chain_blue"].update(structural(fresh, raw, ada["box"]))
    print("chain blue", results["chain_blue"], flush=True)

    raw, _, s, status = await from_stored(fresh, sheet, BLUE, "stored-image edit: blue")
    keep("stored-blue", raw)
    results["stored_blue"] = {"status": status, "latency_s": round(s, 1)}
    if raw:
        results["stored_blue"].update(structural(fresh, raw, ada["box"]))
    print("stored blue", results["stored_blue"], flush=True)

    results["retention"] = []
    for minutes in (3, 6, 12):
        wait = born + 60 * minutes - time.time()
        if wait > 0:
            time.sleep(wait)
        raw, _, s, status = await chained(fresh_id, "Make the rain on the window a little heavier.", f"chain at {minutes} min")
        row = {"after_min": round((time.time() - born) / 60, 1), "status": status, "latency_s": round(s, 1)}
        results["retention"].append(row)
        print("retention", row, flush=True)
        write_json(S4 / "results.json", results)
    write_json(S4 / "results.json", results)


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
