"""Spike 2: character consistency across panels.

Reference sheet per character, then every shot as a 16:9 panel from those
references, three ways (Responses low, Responses high, images/edits low), plus
one multi-turn edit chained with previous_response_id. Contact sheets go to
spikes/out/ for a human to judge.

Finished images are recorded in out/s2_manifest.json; reruns skip them, so a
rerun never pays twice.

Usage: spikes/.venv/bin/python spikes/s2_consistency.py
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont

from common import (
    BASE_URL,
    IMAGE_MODEL,
    OUT,
    PRICE_IMAGE,
    api_key,
    client,
    data_url,
    image_from_response,
    image_tool,
    log_cost,
    reserve,
    save_image,
    timed,
    write_json,
)

SPIKE = "s2"
MANIFEST = OUT / "s2_manifest.json"
STYLE = "clean pencil storyboard sketch, light grey wash, one accent colour"
PANEL_SIZE = "1792x1024"  # images/edits: 16:9-ish, returns 2016x1152
# The Responses image tool rejects 1792x1024 (HTTP 400 "unknown value"); 1536x1024 (3:2) is the widest it took.
RESPONSES_PANEL_SIZE = "1536x1024"
EDIT_PROMPT = "make her raincoat red, keep everything else the same"
WORKERS = 3


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}


manifest = load_manifest()


def record(key: str, value: dict[str, Any]) -> None:
    manifest[key] = value
    write_json(MANIFEST, manifest)


def once(key: str, make: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    if key in manifest and Path(manifest[key]["path"]).exists():
        return manifest[key]
    value = make()
    record(key, value)
    print(f"  {key}: {value['latency_s']} s -> {Path(value['path']).name}", flush=True)
    return value


def responses_image(key: str, content: list[dict] | str, size: str, strength: str,
                    previous_response_id: str | None = None) -> dict[str, Any]:
    reserve(PRICE_IMAGE)
    kwargs: dict[str, Any] = {}
    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id
    with timed() as t:
        resp = client().responses.create(
            model=IMAGE_MODEL,
            input=content if isinstance(content, str) else [{"role": "user", "content": content}],
            tools=[image_tool(size, strength)],
            **kwargs,
        )
    log_cost(spike=SPIKE, model=IMAGE_MODEL, latency_s=t.seconds, cost_usd=PRICE_IMAGE, note=key)
    path = save_image(image_from_response(resp), OUT / key)
    return {"path": str(path), "latency_s": round(t.seconds, 1), "response_id": resp.id}


def edits_endpoint_image(key: str, prompt: str, refs: list[Path], strength: str) -> dict[str, Any]:
    reserve(PRICE_IMAGE)
    body = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "images": [{"image_url": data_url(p)} for p in refs],
        "size": PANEL_SIZE,
        "reasoning_strength": strength,
    }
    req = urllib.request.Request(
        f"{BASE_URL}/images/edits", data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
    )
    with timed() as t:
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"images/edits {e.code}: {e.read()[:500]!r}") from None
    log_cost(spike=SPIKE, model=IMAGE_MODEL, latency_s=t.seconds, cost_usd=PRICE_IMAGE, note=key)
    path = save_image(base64.b64decode(data["data"][0]["b64_json"]), OUT / key)
    return {"path": str(path), "latency_s": round(t.seconds, 1)}


def reference_prompt(c: dict) -> str:
    return (
        f"Character reference sheet for an original character named {c['name']}: {c['canonical_description']}. "
        "Show the same character twice side by side: a front view and a three-quarter view, full body, "
        "neutral standing pose, identical outfit and colours in both views. Plain light grey background, "
        "no text, no props, no scenery. Style: clean pencil storyboard sketch with flat colour."
    )


def panel_prompt(shot: dict, chars: dict[str, dict]) -> str:
    cast = "; ".join(f"{chars[i]['name']}: {chars[i]['canonical_description']}" for i in shot["character_ids"])
    return (
        f"Storyboard panel, shot {shot['shot_number']}, {shot['framing'].replace('_', ' ')} framing, 16:9. "
        f"Setting: {shot['setting']}. Action: {shot['action']}. "
        + (f"Characters: {cast}. Draw each character exactly as in the attached reference sheets: same face, "
           "hair, outfit and colours. " if cast else "")
        + f"Style: {STYLE}. No text, captions or panel borders."
    )


def refs_for(shot: dict, ref_paths: dict[str, Path]) -> list[Path]:
    return [ref_paths[i] for i in shot["character_ids"]] or list(ref_paths.values())


def contact_sheet(title: str, items: list[tuple[str, Path]], out: Path, cols: int = 3, thumb_w: int = 560) -> Path:
    imgs = [Image.open(p).convert("RGB") for _, p in items]
    thumb_h = max(round(thumb_w * im.height / im.width) for im in imgs)
    label_h, pad, head = 34, 16, 56
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (thumb_w + pad) + pad, head + rows * (thumb_h + label_h + pad)), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 22)
        small = ImageFont.truetype("DejaVuSans.ttf", 17)
    except OSError:
        font = small = ImageFont.load_default()
    draw.text((pad, 16), title, fill="black", font=font)
    for n, ((label, _), im) in enumerate(zip(items, imgs)):
        x = pad + (n % cols) * (thumb_w + pad)
        y = head + (n // cols) * (thumb_h + label_h + pad)
        im.thumbnail((thumb_w, thumb_h))
        sheet.paste(im, (x, y))
        draw.text((x, y + thumb_h + 6), label, fill="#333333", font=small)
    sheet.save(out)
    return out


def main() -> None:
    sb = json.loads((OUT / "s1_storyboard.json").read_text())["storyboard"]
    chars = {c["id"]: c for c in sb["characters"]}
    shots = sb["shots"]

    print("a) reference sheets")
    ref_paths = {cid: Path(once(f"ref_{cid}", lambda c=c: responses_image(
        f"ref_{c['id']}", reference_prompt(c), "1024x1024", "high"))["path"]) for cid, c in chars.items()}

    def content_for(shot: dict) -> list[dict]:
        return [{"type": "input_text", "text": panel_prompt(shot, chars)}] + [
            {"type": "input_image", "image_url": data_url(p)} for p in refs_for(shot, ref_paths)]

    jobs: list[tuple[str, Callable[[], dict[str, Any]]]] = []
    for strength in ("low", "high"):
        for s in shots:
            key = f"A_{strength}_shot{s['shot_number']}"
            jobs.append((key, lambda key=key, s=s, strength=strength: responses_image(
                key, content_for(s), RESPONSES_PANEL_SIZE, strength)))
    for s in shots:
        key = f"B_low_shot{s['shot_number']}"
        jobs.append((key, lambda key=key, s=s: edits_endpoint_image(
            key, panel_prompt(s, chars), refs_for(s, ref_paths), "low")))

    print(f"b) {len(jobs)} panels, {WORKERS} at a time")
    failures: dict[str, str] = {}

    def run(job: tuple[str, Callable[[], dict[str, Any]]]) -> None:
        key, make = job
        try:
            once(key, make)
        except Exception as e:  # keep going; report per panel
            failures[key] = f"{type(e).__name__}: {e}"
            print(f"  {key}: FAILED {failures[key]}", flush=True)

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(run, jobs))

    print("c) multi-turn edit on A_high shot 2")
    base = manifest.get("A_high_shot2")
    if base:
        once("A_high_shot2_edit_red", lambda: responses_image(
            "A_high_shot2_edit_red", EDIT_PROMPT, RESPONSES_PANEL_SIZE, "high", previous_response_id=base["response_id"]))

    print("d) contact sheets")
    refs_sheet = contact_sheet("Reference sheets (Responses API, high)",
                               [(chars[c]["name"], p) for c, p in ref_paths.items()], OUT / "s2_sheet_refs.png",
                               cols=2, thumb_w=520)
    sheets = {"refs": str(refs_sheet)}
    for prefix, title in (("A_low", "A: Responses API, refs as input_image, reasoning low"),
                          ("A_high", "A: Responses API, refs as input_image, reasoning high"),
                          ("B_low", "B: POST /v1/images/edits, refs as images[], reasoning low")):
        items = []
        for s in shots:
            m = manifest.get(f"{prefix}_shot{s['shot_number']}")
            if m:
                items.append((f"Shot {s['shot_number']} {s['framing']}  {m['latency_s']} s", Path(m["path"])))
        if items:
            sheets[prefix] = str(contact_sheet(title, items, OUT / f"s2_sheet_{prefix}.png"))
    if "A_high_shot2_edit_red" in manifest:
        sheets["edit"] = str(contact_sheet(
            f'Edit via previous_response_id: "{EDIT_PROMPT}"',
            [("Before (A high, shot 2)", Path(manifest["A_high_shot2"]["path"])),
             (f"After  {manifest['A_high_shot2_edit_red']['latency_s']} s",
              Path(manifest["A_high_shot2_edit_red"]["path"]))],
            OUT / "s2_edit_before_after.png", cols=2, thumb_w=760))

    write_json(OUT / "s2_summary.json", {"sheets": sheets, "failures": failures})
    print(json.dumps({"sheets": sheets, "failures": failures}, indent=2))
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
