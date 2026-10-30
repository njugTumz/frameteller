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
class OutfitChange:
    """From this shot on, the character wears this look, until a later change (ADR 0018). EVERYDAY: back to the
    canonical description's clothes."""

    character_id: str
    look_id: str
    from_shot_id: str


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
    # Where this shot's voice starts in its turn, once a sibling shot of the same turn was deleted: the deleted
    # shot's stretch is then skipped rather than handed to the next shot. None: shots share the turn in order.
    voice_from_ms: int | None = None

    def __post_init__(self) -> None:
        if self.number < 1:
            raise InvalidValueError("shot numbers start at 1")
        if self.duration_ms <= 0:
            raise InvalidValueError(f"shot {self.number}: duration_ms must be positive")
        if not self.source_turn_ids:
            raise InvalidValueError(f"shot {self.number}: needs at least one source turn")
        if self.voice_from_ms is not None and self.voice_from_ms < 0:
            raise InvalidValueError(f"shot {self.number}: voice_from_ms must not be negative")


def voice_offsets(shots: list[Shot]) -> list[int]:
    """Where each of one turn's shots, in story order, starts in the turn's recording: back to back, unless a deleted
    sibling left a gap (`voice_from_ms`)."""
    out, elapsed = [], 0
    for s in shots:
        start = s.voice_from_ms if s.voice_from_ms is not None else elapsed
        out.append(start)
        elapsed = start + s.duration_ms
    return out
