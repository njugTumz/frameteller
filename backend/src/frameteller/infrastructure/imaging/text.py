"""Text on images with Pillow's bundled font, so the slim container needs no system fonts."""

from __future__ import annotations

from functools import cache

from PIL import ImageDraw, ImageFont

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

INK = (34, 31, 28)
PAPER = (244, 241, 234)
MUTED = (110, 104, 96)


@cache
def font(size: int) -> Font:
    return ImageFont.load_default(size)


def wrap(draw: ImageDraw.ImageDraw, text: str, size: int, width: int, max_lines: int = 0) -> list[str]:
    """Greedy word wrap to `width` pixels. With `max_lines`, the last line ends in an ellipsis if cut."""
    lines: list[str] = []
    for word in text.split():
        candidate = f"{lines[-1]} {word}" if lines else word
        if lines and draw.textlength(candidate, font=font(size)) <= width:
            lines[-1] = candidate
        else:
            lines.append(word)
    if max_lines and len(lines) > max_lines:
        last = lines[max_lines - 1]
        while last and draw.textlength(last + "…", font=font(size)) > width:
            last = last[:-1]
        lines = [*lines[: max_lines - 1], last.rstrip() + "…"]
    return lines


def line_height(size: int) -> int:
    return round(size * 1.3)
