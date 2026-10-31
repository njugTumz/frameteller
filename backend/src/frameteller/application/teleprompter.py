"""Teleprompter: follow a reader through their script and find where each paragraph ends (ADR 0015).

The transcriber's words are matched against the end of the current paragraph. Matching is fuzzy, so misheard
words ("Lena" heard as "Lina", a dropped "the") still line up: a paragraph counts as read when most of its last
words were heard, in order, including one of its last two, and at least half of all its words were. The session
then cuts the beat there once the reader pauses, or at once if they have already read on into the next paragraph.

Japanese and Chinese have no spaces between words, so there every character is a unit to match, and the tail is
the paragraph's last TAIL_CHARACTERS characters. Other scripts (Korean, Hindi, Arabic) match by words, as written.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from difflib import SequenceMatcher

from frameteller.domain import spaceless

TAIL_WORDS = 5  # the paragraph's last words that must be heard
TAIL_CHARACTERS = 8  # or, in Japanese and Chinese, its last characters
MIN_TAIL_SHARE = 0.6  # of them, at least this share, in order
MIN_PARAGRAPH_SHARE = 0.5  # and the reader has said at least half as many words as the paragraph has
MIN_COVERAGE = 0.5  # and at least half the paragraph's words were heard, in order: it was this paragraph
SIMILAR = 0.72  # two words match when their letters are this similar ("lina" ~ "lena")
NUMBERS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
    "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten", "12": "twelve",
}  # fmt: skip


def _latin(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", plain)
    return [NUMBERS.get(w, w) for w in words]


def normalise(text: str) -> list[str]:
    """Lowercase words without accents or punctuation; digits spelled out as the transcriber may write them.
    Kana and Han are one unit per character; other scripts keep their letters and marks (Hindi's vowel signs)."""
    units: list[str] = []
    latin, other = "", ""
    for ch in unicodedata.normalize("NFKC", text):
        if unicodedata.normalize("NFKD", ch)[0].isascii():  # "é" too: _latin drops its accent
            if other:
                units.append(other.casefold())
                other = ""
            latin += ch
            continue
        units += _latin(latin)
        latin = ""
        if spaceless(ch):
            if other:
                units.append(other.casefold())
                other = ""
            if ch.isalnum():
                units.append(ch)
        elif unicodedata.category(ch)[0] in "LMN":
            other += ch
        elif other:
            units.append(other.casefold())
            other = ""
    if other:
        units.append(other.casefold())
    return units + _latin(latin)


def similar(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) <= 2:
        return False  # short words must match exactly: "a" is not "i"
    return SequenceMatcher(None, a, b).ratio() >= SIMILAR


def _align(tail: Sequence[str], heard: Sequence[str]) -> tuple[int, int, int, bool]:
    """Longest in-order fuzzy match of `tail` within `heard`: (matched words, index of the last matched heard word,
    index of the last matched tail word, whether one of the tail's last two words matched). Prefers the earliest
    end among equally good matches."""
    n, m = len(tail), len(heard)
    # best[i][j]: (count, last heard index, last tail index, a last-two tail word matched) for tail[:i], heard[:j]
    best = [[(0, -1, -1, False)] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            options = [best[i - 1][j], best[i][j - 1]]
            if similar(tail[i - 1], heard[j - 1]):
                count, _, _, late = best[i - 1][j - 1]
                options.append((count + 1, j - 1, i - 1, late or i >= n - 1))
            best[i][j] = max(options, key=lambda o: (o[0], o[3], -o[1] if o[1] >= 0 else 0))
    return best[n][m]


def paragraph_end(paragraph: str, heard: Sequence[str]) -> int | None:
    """The index in `heard` (normalised words since the last cut) where the paragraph's reading ends, if it does."""
    words = normalise(paragraph)
    if not words or not heard:
        return None
    if len(heard) < max(1, MIN_PARAGRAPH_SHARE * len(words)):
        return None
    tail = words[-(TAIL_CHARACTERS if spaceless(words[-1][0]) else TAIL_WORDS) :]
    count, last, last_tail, late = _align(tail, heard)
    needed = max(min(2, len(tail)), round(MIN_TAIL_SHARE * len(tail)))
    if count < needed or not late:
        return None
    # A few tail words can turn up by chance in a long, unrelated reading ("all" ~ "alley", "it"), so the
    # paragraph as a whole must have been read too.
    covered, _, _, _ = _align(words, heard[: last + 1])
    if covered < MIN_COVERAGE * len(words):
        return None
    # A misheard last word ("roof" heard as "ruf") still belongs to this paragraph: take the words it was owed.
    return min(last + len(tail) - 1 - last_tail, len(heard) - 1)
