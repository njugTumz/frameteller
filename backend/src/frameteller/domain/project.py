"""The Project aggregate: the only way to change shots, panels and the cast."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace

from frameteller.domain.characters import Character, CharacterBible
from frameteller.domain.errors import (
    CastNotApprovedError,
    InvalidValueError,
    ShotOrderError,
    UnknownShotError,
    UnknownTurnError,
)
from frameteller.domain.exports import AnimaticExport
from frameteller.domain.media import MediaRef
from frameteller.domain.narration import Narration
from frameteller.domain.panels import Panel
from frameteller.domain.shots import Shot
from frameteller.domain.style import PanelStyle
from frameteller.domain.transcript import TranscriptTurn


@dataclass(slots=True)
class Project:
    id: str
    title: str = ""
    style: PanelStyle = PanelStyle.PENCIL
    bible: CharacterBible = field(default_factory=CharacterBible)
    turns: list[TranscriptTurn] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    panels: dict[str, Panel] = field(default_factory=dict)
    narrations: dict[str, Narration] = field(default_factory=dict)  # by session tag, kept only with consent
    animatic: AnimaticExport | None = None  # the latest export
    share_token: str | None = None  # the read-only share link, until revoked
    share_public: bool = False  # the owner let search engines index the share page
    usage: dict[str, int] = field(default_factory=dict)  # public-demo allowances used, e.g. renders, exports

    # ---- transcript and characters ----

    def add_turn(self, turn: TranscriptTurn) -> None:
        if all(t.id != turn.id for t in self.turns):
            self.turns.append(turn)

    def turn(self, turn_id: str) -> TranscriptTurn:
        for t in self.turns:
            if t.id == turn_id:
                return t
        raise UnknownTurnError(f"no turn {turn_id!r}")

    def correct_turn(self, turn_id: str, text: str) -> TranscriptTurn:
        """Replace a turn's text (a misheard word fixed by the user). Its timing stays."""
        if not text.strip():
            raise InvalidValueError("a corrected turn needs some text")
        corrected = replace(self.turn(turn_id), text=text.strip())
        self.turns = [corrected if t.id == turn_id else t for t in self.turns]
        return corrected

    def shots_from_turn(self, turn_id: str) -> list[Shot]:
        return [s for s in self.shots if turn_id in s.source_turn_ids]

    def upsert_character(self, character: Character) -> None:
        self.bible.upsert(character)

    def rename_character(self, character_id: str, name: str) -> Character:
        return self.bible.rename(character_id, name)

    def remove_character(self, character_id: str) -> list[Shot]:
        """Remove a character from the cast and from every shot. The shots keep their action text.

        Returns the shots that changed; their panels still show the character, so they are marked outdated.
        """
        self.bible.remove(character_id)
        return self._recast(character_id, None)

    def merge_character(self, character_id: str, into: str) -> list[Shot]:
        """The same character was cast twice ("Ember" was Pip): every shot of `character_id` now shows `into`.

        Returns the shots that changed, with their panels marked outdated.
        """
        if character_id == into:
            raise InvalidValueError("a character cannot be merged into itself")
        self.bible.get(into)
        self.bible.remove(character_id)
        return self._recast(character_id, into)

    def revise_shot(self, shot_id: str, character_ids: tuple[str, ...], action: str) -> Shot:
        """A later turn revealed who or what was in this shot. Its panel shows the old guess: outdated."""
        self.bible.require(character_ids)
        if not action.strip():
            raise InvalidValueError("a revised shot needs an action")
        i = next((i for i, s in enumerate(self.shots) if s.id == shot_id), None)
        if i is None:
            raise UnknownShotError(f"no shot {shot_id!r}")
        self.shots[i] = replace(self.shots[i], character_ids=tuple(dict.fromkeys(character_ids)), action=action.strip())
        self._mark_outdated([shot_id])
        return self.shots[i]

    def drop_unused_characters(self, character_ids: Iterable[str]) -> list[str]:
        """Remove those of `character_ids` that no shot shows any more (a guess a reveal replaced)."""
        used = {c for s in self.shots for c in s.character_ids}
        dropped = [c for c in dict.fromkeys(character_ids) if c in self.bible and c not in used]
        for c in dropped:
            self.bible.remove(c)
        return dropped

    def _recast(self, old: str, new: str | None) -> list[Shot]:
        changed = []
        for i, s in enumerate(self.shots):
            if old not in s.character_ids:
                continue
            ids = [new if c == old else c for c in s.character_ids if new is not None or c != old]
            self.shots[i] = replace(s, character_ids=tuple(dict.fromkeys(c for c in ids if c is not None)))
            changed.append(self.shots[i])
        self._mark_outdated(s.id for s in changed)
        return changed

    def _mark_outdated(self, shot_ids: Iterable[str]) -> None:
        for shot_id in shot_ids:
            if (panel := self.panels.get(shot_id)) is not None and panel.revision > 0:
                panel.outdated = True

    # ---- the narrator's recording ----

    def keep_narration(self, narration: Narration) -> None:
        self.narrations[narration.session] = narration

    def forget_narrations(self) -> list[MediaRef]:
        """Drop every recording; returns them so the caller can delete the files."""
        refs = [n.recording for n in self.narrations.values()]
        self.narrations = {}
        return refs

    # ---- allowances ----

    def count_use(self, kind: str) -> int:
        """One more use of a limited action (a render, an export). Returns the new count."""
        self.usage[kind] = self.usage.get(kind, 0) + 1
        return self.usage[kind]

    # ---- sharing ----

    def share(self, token: str, *, public: bool = False) -> str:
        """Turn the read-only link on, or change whether it is public. Sharing again keeps the link people
        already have. A link is unlisted (never indexed) unless the owner makes it public."""
        if self.share_token is None:
            self.share_token = token
        self.share_public = public
        return self.share_token

    def unshare(self) -> str | None:
        """Turn the link off. Returns the revoked token so the caller can forget it."""
        token, self.share_token, self.share_public = self.share_token, None, False
        return token

    # ---- exports ----

    def record_animatic(self, export: AnimaticExport) -> MediaRef | None:
        """Keep the latest animatic. Returns the one it replaces, for the caller to delete."""
        previous = self.animatic.video if self.animatic and self.animatic.video != export.video else None
        self.animatic = export
        return previous

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

    def replace_shots(self, old_ids: Sequence[str], new: Sequence[Shot]) -> list[Shot]:
        """Swap shots for re-directed ones, where the first old shot was (or at the end), and renumber 1..n.

        Panels of the removed shots are dropped: they show what the old shots said.
        """
        old = set(old_ids)
        if missing := old - {s.id for s in self.shots}:
            raise UnknownShotError(f"no shots {sorted(missing)}")
        for s in new:
            self.bible.require(s.character_ids)
        known = {t.id for t in self.turns}
        for s in new:
            if missing_turns := set(s.source_turn_ids) - known:
                raise ShotOrderError(f"a new shot cites unknown turns {sorted(missing_turns)}")
        at = next((i for i, s in enumerate(self.shots) if s.id in old), len(self.shots))  # no old shot before it
        kept = [s for s in self.shots if s.id not in old]
        ordered = [*kept[:at], *new, *kept[at:]]
        self.shots = [replace(s, number=n) for n, s in enumerate(ordered, start=1)]
        for shot_id in old:
            self.panels.pop(shot_id, None)
        self._check_contiguous()
        new_ids = {s.id for s in new}
        return [s for s in self.shots if s.id in new_ids]

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
