"""Text on images in any of our languages, with fonts bundled in the package, so the slim container needs none.

Pillow's bundled font draws Latin text; Noto fonts (fonts/README.md) draw Japanese, Korean, Chinese, Hindi and
Arabic. A line is cut into runs, one per font: Latin words inside Hindi or Arabic ("frameteller.com") keep the
Latin font, while in Chinese, Japanese and Korean the CJK font draws the whole line (it has Latin letters too).
Spaces and punctuation between two runs go with the line's own script, as Unicode's bidirectional rules place
them. Each run is shaped by raqm (HarfBuzz for Devanagari conjuncts and Arabic joining, FriBidi for direction),
and a line that starts in Arabic is laid out right to left: its runs are placed from the right.
"""

from __future__ import annotations

import re
import unicodedata
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from frameteller.domain import join, tokens

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

INK = (34, 31, 28)
PAPER = (244, 241, 234)
MUTED = (110, 104, 96)

FONTS = Path(__file__).parent / "fonts"
LATIN = "latin"  # Pillow's bundled font
FILES = {
    "ja": "NotoSansJP-Regular.otf",
    "ko": "NotoSansKR-Regular.otf",
    "zh": "NotoSansSC-Regular.otf",
    "hi": "NotoSansDevanagari-Regular.ttf",
    "ar": "NotoSansArabic-Regular.ttf",
}
CJK = ("ja", "ko", "zh")


def _chars(*ranges: tuple[int, int]) -> re.Pattern[str]:
    return re.compile("[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in ranges) + "]")


ARABIC = _chars((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
DEVANAGARI = _chars((0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x1CD0, 0x1CFF))
HANGUL = _chars((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF))
KANA = _chars((0x3040, 0x30FF), (0x31F0, 0x31FF), (0xFF66, 0xFF9F))
HAN = _chars((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x20000, 0x3134F))
FULL_WIDTH = _chars((0x3000, 0x303F), (0xFF00, 0xFF65))  # CJK punctuation and full-width forms


@cache
def font(size: int, script: str = LATIN) -> Font:
    if script == LATIN:
        return ImageFont.load_default(size)
    return ImageFont.truetype(str(FONTS / FILES[script]), size, layout_engine=ImageFont.Layout.RAQM)


def _script(ch: str) -> str | None:
    for name, pattern in (("ar", ARABIC), ("hi", DEVANAGARI), ("ko", HANGUL), ("ja", KANA), ("han", HAN)):
        if pattern.match(ch):
            return name
    return None


def base_script(text: str, language: str = "") -> str:
    """The line's own script: the language's when its letters are there, else the first one found."""
    lang = language.split("-")[0].lower()
    found = {s for ch in text if (s := _script(ch))}
    if lang in CJK and found & {"ja", "ko", "han"}:
        return lang
    if lang in ("ar", "hi") and lang in found:
        return lang
    for name in ("ja", "ko", "ar", "hi"):
        if name in found:
            return name
    return "zh" if "han" in found else LATIN


def _key(ch: str, base: str) -> str | None:
    """The font a letter needs, or None for spaces, digits, punctuation and marks (they follow their line)."""
    script = _script(ch)
    if script in ("ja", "ko", "han") or FULL_WIDTH.match(ch):
        return base if base in CJK else ("zh" if script in ("han", None) else script)
    if script is not None:
        return script
    if unicodedata.category(ch).startswith("L"):
        return base if base in CJK else LATIN
    return None


@cache
def _notdef(script: str) -> bytes:
    return _ink(script, chr(0x10FFFD))


@cache
def _ink(script: str, ch: str) -> bytes:
    image = Image.new("L", (64, 64))
    ImageDraw.Draw(image).text((8, 8), ch, font=font(40, script), fill=255)
    return image.tobytes()


def covers(script: str, ch: str) -> bool:
    """Whether the font draws the character (and not its empty box)."""
    return ch.isspace() or _ink(script, ch) != _notdef(script)


def runs(text: str, language: str = "") -> tuple[list[tuple[str, str]], bool]:
    """The line in logical order as (text, font) runs, and whether it reads right to left."""
    base = base_script(text, language)
    keys = [_key(ch, base) for ch in text]
    strong = [k for k in keys if k]
    rtl = bool(strong) and strong[0] == "ar"
    resolved: list[str] = []
    for i, (ch, key) in enumerate(zip(text, keys, strict=True)):
        if key is None:
            before = next((k for k in reversed(keys[:i]) if k), None)
            after = next((k for k in keys[i + 1 :] if k), None)
            if before is not None and before == after:
                key = before
            elif rtl:
                key = "ar"
            else:
                key = before or after or base
            if not covers(key, ch):
                key = LATIN
        resolved.append(key)
    out: list[tuple[str, str]] = []
    for ch, key in zip(text, resolved, strict=True):
        if out and out[-1][1] == key:
            out[-1] = (out[-1][0] + ch, key)
        else:
            out.append((ch, key))
    return out, rtl


def _direction(script: str) -> str | None:
    return "rtl" if script == "ar" else None


def textlength(text: str, size: int, language: str = "") -> float:
    parts, _ = runs(text, language)
    return sum(font(size, k).getlength(t, direction=_direction(k)) for t, k in parts)


def draw_line(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    size: int,
    fill: tuple[int, ...],
    *,
    language: str = "",
    anchor: str = "la",
) -> None:
    """One line at `xy`, anchored like Pillow's: l, m or r across; a (ascender), t (top of the ink) or s (baseline)
    down."""
    parts, rtl = runs(text, language)
    if len(parts) <= 1:
        script = parts[0][1] if parts else LATIN
        draw.text(xy, text, font=font(size, script), fill=fill, anchor=anchor, direction=_direction(script))
        return
    widths = [font(size, k).getlength(t, direction=_direction(k)) for t, k in parts]
    x, y = xy
    total = sum(widths)
    left = {"l": x, "m": x - total / 2, "r": x - total}[anchor[0]]
    if anchor[1] == "s":
        baseline = y
    elif anchor[1] == "t":
        tops = [draw.textbbox((0, 0), t, font=font(size, k), anchor="ls", direction=_direction(k))[1] for t, k in parts]
        baseline = y - min(tops)
    else:
        baseline = y + max(font(size, k).getmetrics()[0] for _, k in parts)  # type: ignore[union-attr]
    placed = list(zip(parts, widths, strict=True))
    for (t, k), width in reversed(placed) if rtl else placed:
        draw.text((left, baseline), t, font=font(size, k), fill=fill, anchor="ls", direction=_direction(k))
        left += width


def wrap(
    draw: ImageDraw.ImageDraw, text: str, size: int, width: int, max_lines: int = 0, *, language: str = ""
) -> list[str]:
    """Greedy word wrap to `width` pixels (by characters in Japanese and Chinese). With `max_lines`, the last line
    ends in an ellipsis if cut. A line that fits stays as written."""
    if textlength(text.strip(), size, language) <= width:
        return [text.strip()] if text.strip() else []
    lines: list[list[str]] = []
    for word in tokens(text):
        if lines and textlength(join([*lines[-1], word]), size, language) <= width:
            lines[-1].append(word)
        else:
            lines.append([word])
    joined = [join(line) for line in lines]
    if max_lines and len(joined) > max_lines:
        last = joined[max_lines - 1]
        while last and textlength(last + "…", size, language) > width:
            last = last[:-1]
        joined = [*joined[: max_lines - 1], last.rstrip() + "…"]
    return joined


def line_height(size: int) -> int:
    return round(size * 1.3)
