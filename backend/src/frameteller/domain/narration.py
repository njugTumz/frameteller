"""The narrator's own recording, kept only with consent, for the animatic's voice track."""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.domain.errors import InvalidValueError
from frameteller.domain.media import MediaRef


@dataclass(frozen=True, slots=True)
class Narration:
    """One live session's audio. Turn ids from that session start with its tag ("55a635ca-b2")."""

    session: str
    recording: MediaRef
    duration_ms: int

    def __post_init__(self) -> None:
        if not self.session or "-" in self.session or self.duration_ms <= 0:
            raise InvalidValueError("a narration needs a session tag and some audio")


def session_of(turn_id: str) -> str:
    """The session tag a live turn id starts with."""
    return turn_id.split("-", 1)[0]
