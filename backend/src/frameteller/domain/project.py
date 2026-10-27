"""The Project aggregate: the only way to change shots, panels and the cast."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from frameteller.domain.characters import Character, CharacterBible
from frameteller.domain.errors import CastNotApprovedError, ShotOrderError, UnknownShotError
from frameteller.domain.panels import Panel
from frameteller.domain.shots import Shot
from frameteller.domain.transcript import TranscriptTurn


@dataclass(slots=True)
class Project:
    id: str
    title: str = ""
    bible: CharacterBible = field(default_factory=CharacterBible)
    turns: list[TranscriptTurn] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    panels: dict[str, Panel] = field(default_factory=dict)

    # ---- transcript and characters ----

    def add_turn(self, turn: TranscriptTurn) -> None:
        if all(t.id != turn.id for t in self.turns):
            self.turns.append(turn)

    def upsert_character(self, character: Character) -> None:
        self.bible.upsert(character)

    # ---- shots ----

    def shot(self, shot_id: str) -> Shot:
        for s in self.shots:
            if s.id == shot_id:
                return s
        raise UnknownShotError(f"no shot {shot_id!r}")

    def append_shots(self, shots: Sequence[Shot]) -> None:
        """Append shots after the last one. They must continue the numbering and use known characters."""
        for s in shots:
            self.bible.require(s.character_ids)
        expected = range(len(self.shots) + 1, len(self.shots) + len(shots) + 1)
        if [s.number for s in shots] != list(expected):
            raise ShotOrderError(f"new shots must be numbered {list(expected)}, got {[s.number for s in shots]}")
        known = {t.id for t in self.turns}
        for s in shots:
            if missing := set(s.source_turn_ids) - known:
                raise ShotOrderError(f"shot {s.number} cites unknown turns {sorted(missing)}")
        self.shots.extend(shots)
        self._check_contiguous()

    def reorder_shots(self, shot_ids: Sequence[str]) -> None:
        """Put shots in the given order and renumber 1..n. Must name every shot exactly once."""
        if sorted(shot_ids) != sorted(s.id for s in self.shots):
            raise ShotOrderError("a reorder must list every shot exactly once")
        by_id = {s.id: s for s in self.shots}
        self.shots = [replace(by_id[sid], number=n) for n, sid in enumerate(shot_ids, start=1)]
        self._check_contiguous()

    def _check_contiguous(self) -> None:
        if [s.number for s in self.shots] != list(range(1, len(self.shots) + 1)):
            raise ShotOrderError("shot numbers must run 1..n without gaps")

    # ---- panels ----

    def require_cast_approved(self) -> None:
        if not self.bible.is_approved:
            raise CastNotApprovedError("approve the cast before drawing panels")

    def panel(self, shot_id: str) -> Panel:
        self.shot(shot_id)
        return self.panels.setdefault(shot_id, Panel(shot_id=shot_id))
