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

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms < self.start_ms:
            raise InvalidValueError(f"turn {self.id}: need 0 <= start_ms <= end_ms")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms
