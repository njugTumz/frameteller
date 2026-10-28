"""Server-side compositing of geometry layers with Pillow (ADR 0010)."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence

from PIL import Image

from frameteller.application.ports import CutoutLayer
from frameteller.domain import Size

WEBP_QUALITY = 90


class PillowCompositor:
    """Paste RGBA cut-outs on a clean plate. Runs in a worker thread so the event loop stays free."""

    async def compose(self, background: bytes, layers: Sequence[CutoutLayer], size: Size) -> bytes:
        return await asyncio.to_thread(compose, background, layers, size)


def compose(background: bytes, layers: Sequence[CutoutLayer], size: Size) -> bytes:
    with Image.open(io.BytesIO(background)) as plate:
        canvas = plate.convert("RGBA")
    if canvas.size != (size.width, size.height):  # an edit may come back at another resolution
        canvas = canvas.resize((size.width, size.height), Image.Resampling.LANCZOS)
    for layer in layers:
        with Image.open(io.BytesIO(layer.image)) as raw:
            cutout = raw.convert("RGBA")
        if layer.scale != 1.0:
            width, height = max(1, round(cutout.width * layer.scale)), max(1, round(cutout.height * layer.scale))
            cutout = cutout.resize((width, height), Image.Resampling.LANCZOS)
        _paste(canvas, cutout, layer)
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "WEBP", quality=WEBP_QUALITY)
    return out.getvalue()


def _paste(canvas: Image.Image, cutout: Image.Image, layer: CutoutLayer) -> None:
    """Alpha-paste with the part outside the canvas clipped (alpha_composite refuses negative offsets)."""
    canvas.paste(cutout, (layer.left, layer.top), cutout)
