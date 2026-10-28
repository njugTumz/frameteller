"""The storyboard sheet as a PDF, drawn with Pillow only: A4 landscape, six shots a page."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence

from PIL import Image, ImageDraw

from frameteller.application.ports import SheetRow
from frameteller.infrastructure.imaging.text import INK, MUTED, PAPER, font, line_height, wrap

DPI = 150
PAGE_W, PAGE_H = 1754, 1240  # A4 landscape at 150 dpi
MARGIN, GUTTER = 70, 36
COLUMNS, ROWS = 3, 2
HEADER_H = 90
PANEL_RATIO = 2 / 3  # panels are 3:2
RULE = (214, 208, 198)


class PillowStoryboardSheet:
    async def render(self, title: str, rows: Sequence[SheetRow]) -> bytes:
        return await asyncio.to_thread(render_pdf, title, rows)


def render_pdf(title: str, rows: Sequence[SheetRow]) -> bytes:
    per_page = COLUMNS * ROWS
    chunks = [rows[i : i + per_page] for i in range(0, len(rows), per_page)] or [[]]
    pages = [_page(title, chunk, n + 1, len(chunks)) for n, chunk in enumerate(chunks)]
    out = io.BytesIO()
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=DPI, title=title or "Storyboard")
    return out.getvalue()


def _page(title: str, rows: Sequence[SheetRow], number: int, total: int) -> Image.Image:
    page = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    draw = ImageDraw.Draw(page)
    draw.text((MARGIN, MARGIN - 20), title.strip() or "Untitled story", font=font(40), fill=INK)
    draw.text((PAGE_W - MARGIN, MARGIN - 8), f"Page {number} of {total}", font=font(22), fill=MUTED, anchor="ra")
    draw.line((MARGIN, MARGIN + HEADER_H - 30, PAGE_W - MARGIN, MARGIN + HEADER_H - 30), fill=RULE, width=2)

    cell_w = (PAGE_W - 2 * MARGIN - (COLUMNS - 1) * GUTTER) // COLUMNS
    cell_h = (PAGE_H - 2 * MARGIN - HEADER_H - (ROWS - 1) * GUTTER) // ROWS
    panel_h = round(cell_w * PANEL_RATIO)
    for i, row in enumerate(rows):
        left = MARGIN + (i % COLUMNS) * (cell_w + GUTTER)
        top = MARGIN + HEADER_H + (i // COLUMNS) * (cell_h + GUTTER)
        _panel(page, draw, row.image, (left, top, left + cell_w, top + panel_h))
        _caption(draw, row, left, top + panel_h + 12, cell_w, top + cell_h)
    return page


def _panel(page: Image.Image, draw: ImageDraw.ImageDraw, data: bytes | None, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    if data is None:
        draw.rectangle(box, fill=(232, 228, 220), outline=RULE, width=2)
        draw.text(((left + right) // 2, (top + bottom) // 2), "Not drawn yet", font=font(26), fill=MUTED, anchor="mm")
        return
    with Image.open(io.BytesIO(data)) as image:
        fitted = image.convert("RGB").resize((right - left, bottom - top), Image.Resampling.LANCZOS)
    page.paste(fitted, (left, top))
    draw.rectangle(box, outline=INK, width=2)


def _caption(draw: ImageDraw.ImageDraw, row: SheetRow, left: int, top: int, width: int, bottom: int) -> None:
    seconds = f"{row.duration_ms / 1000:.1f} s"
    draw.text((left, top), f"Shot {row.number}", font=font(26), fill=INK)
    draw.text((left + width, top + 4), f"{row.framing} · {seconds}", font=font(22), fill=MUTED, anchor="ra")
    y = top + line_height(26) + 4
    room = max(1, (bottom - y) // line_height(21))
    action = wrap(draw, row.action, 21, width, max_lines=max(1, room - (1 if row.dialogue else 0)))
    for line in action:
        draw.text((left, y), line, font=font(21), fill=INK)
        y += line_height(21)
    if row.dialogue and y + line_height(21) <= bottom:
        lines = wrap(draw, f"“{row.dialogue}”", 21, width, max_lines=max(1, (bottom - y) // line_height(21)))
        for line in lines:
            draw.text((left, y), line, font=font(21), fill=MUTED)
            y += line_height(21)
