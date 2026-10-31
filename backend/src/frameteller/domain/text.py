"""Words in any script. Japanese and Chinese are written without spaces, so each of their characters is a unit.

`tokens` splits text into units: space-separated words (English, Korean, Hindi, Arabic), and single kana or Han
characters, each keeping the punctuation that closes it ("猫。") or opens it ("「猫"). `join` puts them back,
with a space only where the script wants one. Captions, turns shared between shots, and the teleprompter all
count with these, so a sentence in Japanese splits and times like one in English.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# Kana and Han: scripts written without spaces between words.
_SPACELESS = "\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f"
# Full-width brackets and punctuation (and the prolonged sound mark, which never starts a line); curly quotes and
# the ellipsis also belong to words in other scripts.
_FULL_OPEN, _FULL_CLOSE = "「『（【〈《〔［｛", "、。，．！？：；」』）】〉》〕］｝‥々〜ー"  # noqa: RUF001
_OPEN, _CLOSE = _FULL_OPEN + "“‘", _FULL_CLOSE + "”’…"  # noqa: RUF001
_TOKEN = re.compile(
    rf"[{_OPEN}]*(?:(?![{_FULL_CLOSE}])[{_SPACELESS}]|[^\s{_SPACELESS}{_FULL_OPEN}{_FULL_CLOSE}]+)[{_CLOSE}]*|[{_OPEN}{_CLOSE}]+"
)
_SPACELESS_CHAR = re.compile(rf"[{_SPACELESS}{_FULL_OPEN}{_FULL_CLOSE}\u3000-\u303f\uff00-\uffef]")
# Han, kana and Hangul: captions in these scripts are measured and split by characters.
_CJK = re.compile(rf"[{_SPACELESS}\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")


def tokens(text: str) -> list[str]:
    """Words, or single characters in a script without spaces, with their punctuation attached."""
    return _TOKEN.findall(text)


def spaceless(ch: str) -> bool:
    """A character written without spaces around it: kana, Han or their punctuation."""
    return bool(_SPACELESS_CHAR.match(ch))


def join(parts: Sequence[str]) -> str:
    """Tokens back into text: a space between two words, none next to a character of a script without spaces."""
    out = ""
    for part in parts:
        if out and not (spaceless(out[-1]) or spaceless(part[0])):
            out += " "
        out += part
    return out


def is_cjk(text: str) -> bool:
    """Chinese, Japanese or Korean: its captions are split by characters, not words."""
    return bool(_CJK.search(text))


def units(text: str) -> int:
    """How much is said, for sharing time: words, or characters in Chinese, Japanese and Korean."""
    if is_cjk(text):
        return sum(1 for ch in text if not ch.isspace() and (ch.isalnum() or _CJK.match(ch)))
    return len(tokens(text))
