"""Transcript turns. Timestamps are turn-level, not word-level (CLAUDE.md section 5)."""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.domain.errors import InvalidValueError


@dataclass(frozen=True, slots=True)
class TranscriptTurn:
    id: str
    text: str
    start_ms: int
    end_ms: int
    speaker: str | None = None
    # From a script (ADR 0015): the paragraph as written, with its framing cues and scene heading. The director
    # reads this instead of `text`, which is what was spoken (translated, when a voice reads another language).
    direction: str = ""
    episode: int = 1

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms < self.start_ms:
            raise InvalidValueError(f"turn {self.id}: need 0 <= start_ms <= end_ms")
        if self.episode < 1:
            raise InvalidValueError(f"turn {self.id}: episodes start at 1")

    @property
    def for_director(self) -> str:
        return self.direction or self.text

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms
