"""Spike 3: click to select with SAM 3.1, then a targeted whole-panel edit.

Uses panel 2 from spike 2 (approach A, high). A concept prompt finds Mira's box,
then a point prompt at the box centre simulates the user's click. SAM output is
parsed only with meta_sam_parser. The mask is also used to measure how much of
the panel outside the selected object changes during an edit.

Usage: spikes/.venv/bin/python spikes/s3_sam_click.py
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
from meta_sam_parser import (
    FramePrompt,
    PromptObject,
    PromptPoint,
    SegmentationBoxRecord,
    SegmentationMaskRecord,
    build_object_prompt,
    decode_mask_to_raster,
    image_segmentation_format,
    parse_responses_stream,
)
from PIL import Image, ImageDraw, ImageFilter

from common import (
    OUT,
    PRICE_SAM_IMAGE,
    SAM_MODEL,
    async_client,
    log_cost,
    reserve,
    timed,
    write_json,
)
from s2_consistency import RESPONSES_PANEL_SIZE, contact_sheet, manifest, once, responses_image

SPIKE = "s3"
CONCEPT = "girl in yellow raincoat"
EDIT_PROMPT = "make the girl in the yellow raincoat larger, keep everything else identical"
CHANGED = 24  # per-channel difference (0-255) that counts as a changed pixel


def png_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


async def segment(img: Image.Image, text: str, label: str) -> tuple[list[Any], float, list[str]]:
    reserve(PRICE_SAM_IMAGE)
    oai = async_client()
    with timed() as t:
        stream = await oai.responses.create(
            model=SAM_MODEL,
            input=[{"role": "user", "content": [
                {"type": "input_text", "text": text},
                {"type": "input_image", "image_url": png_data_url(img)},
            ]}],
            stream=True,
        )
        result = await parse_responses_stream(stream, image_segmentation_format()).final_result()
    log_cost(spike=SPIKE, model=SAM_MODEL, latency_s=t.seconds, cost_usd=PRICE_SAM_IMAGE, note=label)
    diagnostics = [f"{d.severity} {d.code}: {d.message}" for d in getattr(result, "diagnostics", ())]
    return list(result.records), t.seconds, diagnostics


def full_mask(rec: SegmentationMaskRecord, size: tuple[int, int]) -> np.ndarray:
    """Place the box-sized mask raster at its bounds on a full-size canvas."""
    w, h = size
    m = rec.mask
    raster = np.frombuffer(decode_mask_to_raster(m), dtype=np.uint8).reshape(m.height, m.width)
    canvas = np.zeros((h, w), dtype=bool)
    x0, y0 = int(rec.bounds.left), int(rec.bounds.top)
    ph, pw = min(m.height, h - y0), min(m.width, w - x0)
    canvas[y0:y0 + ph, x0:x0 + pw] = raster[:ph, :pw].astype(bool)
    return canvas


def change_outside(before: Image.Image, after: Image.Image, mask: np.ndarray) -> dict[str, float]:
    a = np.asarray(before.convert("RGB"), dtype=np.int16)
    b = np.asarray(after.convert("RGB").resize(before.size), dtype=np.int16)
    changed = np.abs(a - b).max(axis=2) > CHANGED
    # Structural change: blur first so redrawn rain and pencil texture do not count, moved shapes do.
    blur = ImageFilter.GaussianBlur(6)
    ab = np.asarray(before.convert("RGB").filter(blur), dtype=np.int16)
    bb = np.asarray(after.convert("RGB").resize(before.size).filter(blur), dtype=np.int16)
    structural = np.abs(ab - bb).max(axis=2) > CHANGED
    # Grow the mask a little so anti-aliased edges are not counted as "outside".
    grown = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(25))) > 0
    outside = ~grown
    return {
        "changed_outside_pct": round(100 * changed[outside].mean(), 2),
        "changed_inside_pct": round(100 * changed[grown].mean(), 2),
        "structural_outside_pct": round(100 * structural[outside].mean(), 2),
        "structural_inside_pct": round(100 * structural[grown].mean(), 2),
        "size_changed": before.size != after.size,
    }


def main() -> None:
    base = manifest["A_high_shot2"]
    img = Image.open(base["path"])
    w, h = img.size

    # a) concept prompt -> Mira's box
    records, concept_s, diag1 = asyncio.run(segment(img, CONCEPT, "concept: " + CONCEPT))
    boxes = [r for r in records if isinstance(r, SegmentationBoxRecord)]
    if not boxes:
        raise SystemExit(f"no box for {CONCEPT!r}; diagnostics: {diag1}")
    box = max(boxes, key=lambda b: (b.right - b.left) * (b.bottom - b.top))

    # Simulated click at the box centre, already in media pixels (preview -> media scaling is 1:1 here).
    cx = max(0, min(w - 1, int((box.left + box.right) / 2)))
    cy = max(0, min(h - 1, int((box.top + box.bottom) / 2)))
    point_prompt = build_object_prompt(size=(w, h), objects=[
        PromptObject(id=1, prompts=[FramePrompt(frame=0, points=[PromptPoint(cx, cy)])])])

    records, point_s, diag2 = asyncio.run(segment(img, point_prompt, "point click"))
    masks = [r for r in records if isinstance(r, SegmentationMaskRecord)]
    if not masks:
        raise SystemExit(f"no mask for point prompt; diagnostics: {diag2}")
    mask = full_mask(masks[0], (w, h))
    area = int(mask.sum())

    # b) overlay and transparent cut-out
    rgb = np.asarray(img.convert("RGB")).copy()
    tint = np.array([40, 120, 255], dtype=np.float32)
    rgb[mask] = (0.45 * rgb[mask] + 0.55 * tint).astype(np.uint8)
    overlay = Image.fromarray(rgb)
    d = ImageDraw.Draw(overlay)
    d.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), outline="white", width=5)
    d.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill="red")
    overlay.save(OUT / "s3_mask_overlay.png")
    rgba = np.dstack([np.asarray(img.convert("RGB")), (mask * 255).astype(np.uint8)])
    cut = Image.fromarray(rgba, "RGBA")
    cut.crop(cut.getbbox()).save(OUT / "s3_cutout.png")

    # c) targeted whole-panel edit naming the selected object
    edit = once("A_high_shot2_edit_larger", lambda: responses_image(
        "A_high_shot2_edit_larger", EDIT_PROMPT, RESPONSES_PANEL_SIZE, "high",
        previous_response_id=base["response_id"]))
    contact_sheet(f'Targeted edit naming the SAM selection: "{EDIT_PROMPT}"',
                  [("Before (A high, shot 2)", Path(base["path"])),
                   (f"After  {edit['latency_s']} s", Path(edit["path"]))],
                  OUT / "s3_edit_before_after.png", cols=2, thumb_w=760)

    stability = {"larger": change_outside(img, Image.open(edit["path"]), mask)}
    after_records, _, _ = asyncio.run(segment(Image.open(edit["path"]), CONCEPT, "concept on edited panel"))
    after_boxes = [r for r in after_records if isinstance(r, SegmentationBoxRecord)]
    if after_boxes:
        ab = max(after_boxes, key=lambda b: (b.right - b.left) * (b.bottom - b.top))
        stability["larger"]["box_area_ratio"] = round(
            ((ab.right - ab.left) * (ab.bottom - ab.top)) / ((box.right - box.left) * (box.bottom - box.top)), 3)
    if "A_high_shot2_edit_red" in manifest:
        stability["red_coat"] = change_outside(img, Image.open(manifest["A_high_shot2_edit_red"]["path"]), mask)

    summary = {
        "image_size": [w, h],
        "concept_prompt": CONCEPT,
        "concept_latency_s": round(concept_s, 2),
        "concept_boxes": len(boxes),
        "box": [box.left, box.top, box.right, box.bottom],
        "point_prompt": point_prompt,
        "point_latency_s": round(point_s, 2),
        "mask_records": len(masks),
        "mask_encoding": masks[0].mask.encoding,
        "mask_raster": [masks[0].mask.width, masks[0].mask.height],
        "mask_area_px": area,
        "mask_area_pct": round(100 * area / (w * h), 2),
        "diagnostics": diag1 + diag2,
        "edit_latency_s": edit["latency_s"],
        "stability": stability,
    }
    write_json(OUT / "s3_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
