"""Captions of what is said over the animatic: short lines, each shown only while it is spoken.

A shot's caption is the words spoken over it (the transcript with its corrections, the script, or its
translation). Turn timestamps are turn-level (CLAUDE.md section 5), so each shot's words are split into lines of
about 6 to 10 words, and the shot's time is shared between its lines by word count.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from frameteller.domain.animatic import Animatic

MAX_WORDS = 10


@dataclass(frozen=True, slots=True)
class Cue:
    start_ms: int
    end_ms: int
    text: str


def caption_lines(text: str) -> list[str]:
    """Words in balanced lines of at most MAX_WORDS: 13 words make 7 + 6, not 10 + 3."""
    words = text.split()
    if not words:
        return []
    count = math.ceil(len(words) / MAX_WORDS)
    size, extra = divmod(len(words), count)
    lines, at = [], 0
    for i in range(count):
        n = size + (1 if i < extra else 0)
        lines.append(" ".join(words[at : at + n]))
        at += n
    return lines


def caption_cues(animatic: Animatic, captions: Sequence[str] | None = None, offset_ms: int = 0) -> list[Cue]:
    """One cue per line, in timeline order. `captions` replaces each clip's own (a translation), in clip order."""
    texts = list(captions) if captions is not None else [c.caption for c in animatic.clips]
    cues: list[Cue] = []
    for clip, text in zip(animatic.clips, texts, strict=True):
        lines = caption_lines(text)
        total = sum(len(line.split()) for line in lines)
        start, said = clip.start_ms + offset_ms, 0
        for line in lines:
            said += len(line.split())
            end = clip.start_ms + offset_ms + round(clip.duration_ms * said / total)
            if end > start:
                cues.append(Cue(start, end, line))
            start = end
    return cues


def _timestamp(ms: int) -> str:
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def to_srt(cues: Sequence[Cue]) -> str:
    blocks = [f"{n}\n{_timestamp(c.start_ms)} --> {_timestamp(c.end_ms)}\n{c.text}\n" for n, c in enumerate(cues, 1)]
    return "\n".join(blocks)
