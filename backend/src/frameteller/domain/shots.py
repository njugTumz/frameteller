"""Shots: what the director decides for each part of the story."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from frameteller.domain.errors import InvalidValueError


class Framing(StrEnum):
    WIDE = "wide"
    MEDIUM = "medium"
    CLOSE_UP = "close_up"
    OVER_SHOULDER = "over_shoulder"
    INSERT = "insert"


@dataclass(frozen=True, slots=True)
class Shot:
    id: str
    number: int
    framing: Framing
    character_ids: tuple[str, ...]
    setting: str
    action: str
    dialogue: str
    source_turn_ids: tuple[str, ...]
    duration_ms: int
    episode: int = 1  # shots are numbered through the whole story; the studio counts them per episode

    def __post_init__(self) -> None:
        if self.number < 1:
            raise InvalidValueError("shot numbers start at 1")
        if self.duration_ms <= 0:
            raise InvalidValueError(f"shot {self.number}: duration_ms must be positive")
        if not self.source_turn_ids:
            raise InvalidValueError(f"shot {self.number}: needs at least one source turn")
