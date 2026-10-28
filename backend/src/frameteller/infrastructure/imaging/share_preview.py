"""The og:image for share links: 1200x630, the story's title over its first six panels."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence

from PIL import Image, ImageDraw

from frameteller.infrastructure.imaging.text import INK, MUTED, PAPER, font, wrap

WIDTH, HEIGHT = 1200, 630
MARGIN, GUTTER, HEADER = 20, 10, 56
COLUMNS = 3


class PillowSharePreview:
    async def contact_sheet(self, title: str, panels: Sequence[bytes]) -> bytes:
        return await asyncio.to_thread(contact_sheet, title, panels)


def contact_sheet(title: str, panels: Sequence[bytes]) -> bytes:
    sheet = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(sheet)
    [heading] = wrap(draw, title.strip() or "A Frameteller storyboard", 34, WIDTH - 2 * MARGIN - 220, max_lines=1)
    draw.text((MARGIN, MARGIN), heading, font=font(34), fill=INK)
    draw.text((WIDTH - MARGIN, MARGIN + 10), "Frameteller storyboard", font=font(20), fill=MUTED, anchor="ra")
    cell_w = (WIDTH - 2 * MARGIN - (COLUMNS - 1) * GUTTER) // COLUMNS
    cell_h = cell_w * 2 // 3
    for i in range(COLUMNS * 2):
        left = MARGIN + (i % COLUMNS) * (cell_w + GUTTER)
        top = MARGIN + HEADER + (i // COLUMNS) * (cell_h + GUTTER)
        tile = _tile(panels[i], (cell_w, cell_h)) if i < len(panels) else None
        if tile is not None:
            sheet.paste(tile, (left, top))
        else:
            draw.rectangle((left, top, left + cell_w, top + cell_h), fill=(232, 228, 220))
    out = io.BytesIO()
    sheet.save(out, "PNG", optimize=True)
    return out.getvalue()


def _tile(data: bytes, size: tuple[int, int]) -> Image.Image | None:
    """A panel resized to its cell, or None if it cannot be read: a preview never fails over one image."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            return image.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    except (OSError, ValueError):
        return None
