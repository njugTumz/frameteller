"""The Project aggregate: the only way to change shots, panels and the cast."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace

from frameteller.domain.characters import (
    EVERYDAY,
    CastStatus,
    Character,
    CharacterBible,
    Look,
    SheetRefusal,
    sheet_target,
)
from frameteller.domain.errors import (
    CastNotApprovedError,
    InvalidValueError,
    ShotOrderError,
    UnknownShotError,
    UnknownTurnError,
)
from frameteller.domain.exports import AnimaticExport
from frameteller.domain.media import MediaRef
from frameteller.domain.narration import Narration, session_of
from frameteller.domain.panels import Panel
from frameteller.domain.review import SUPERVISOR_LOG_SIZE, Outcome, PanelReview, SheetReview, SupervisorEntry
from frameteller.domain.shots import OutfitChange, Shot, voice_offsets
from frameteller.domain.style import PanelStyle
from frameteller.domain.timing import split_duration
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
    continuity_checks: bool = True  # the continuity supervisor reviews sheets and panels (ADR 0012)
    sheet_reviews: dict[str, SheetReview] = field(default_factory=dict)  # by character id
    # Why a character's sheet could not be drawn, in plain words, until a sheet is drawn for it.
    sheet_failures: dict[str, str] = field(default_factory=dict)
    sheet_refusals: dict[str, SheetRefusal] = field(default_factory=dict)  # by sheet target (ADR 0019)
    supervisor_log: list[SupervisorEntry] = field(default_factory=list)  # oldest first, the last 100
    outfits: list[OutfitChange] = field(default_factory=list)  # who wears which look from which shot (ADR 0018)

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
        self._forget_outfits(character_id)
        return self._recast(character_id, None)

    def merge_character(self, character_id: str, into: str) -> list[Shot]:
        """The same character was cast twice ("Ember" was Pip): every shot of `character_id` now shows `into`.

        Returns the shots that changed, with their panels marked outdated.
        """
        if character_id == into:
            raise InvalidValueError("a character cannot be merged into itself")
        self.bible.get(into)
        self.bible.remove(character_id)
        self._forget_outfits(character_id)
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
            self._forget_outfits(c)
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

    # ---- outfits (ADR 0018) ----

    def look_in(self, shot_id: str, character_id: str) -> Look | None:
        """The look a character wears in a shot: the latest outfit change at or before it. None: everyday clothes."""
        order = {s.id: i for i, s in enumerate(self.shots)}
        if shot_id not in order:
            raise UnknownShotError(f"no shot {shot_id!r}")
        current, best = None, -1
        for change in self.outfits:  # of two changes at the same shot, the later one wins
            i = order.get(change.from_shot_id)
            if change.character_id == character_id and i is not None and best <= i <= order[shot_id]:
                current, best = change, i
        if current is None or current.look_id == EVERYDAY or character_id not in self.bible:
            return None
        character = self.bible.get(character_id)
        return character.look(current.look_id) if character.has_look(current.look_id) else None

    def cast_in(self, shot_id: str) -> list[Character]:
        """The shot's characters as it shows them: each in the look they wear by then, with that look's sheet."""
        shot = self.shot(shot_id)
        return [self.bible.get(c).dressed(self.look_in(shot_id, c)) for c in shot.character_ids if c in self.bible]

    def change_outfit(self, character_id: str, look: Look | None, from_shot_id: str) -> list[str]:
        """From `from_shot_id` on, the character wears `look` (None: everyday clothes again) until the next change.

        Returns the shots that now show other clothes; their drawn panels are outdated.
        """
        self.shot(from_shot_id)
        before, approved = self._wearing(character_id), self.bible.is_approved
        if look is not None:
            self.bible.set_look(character_id, look)
        self.outfits = [
            o for o in self.outfits if not (o.character_id == character_id and o.from_shot_id == from_shot_id)
        ]
        self.outfits.append(OutfitChange(character_id, look.id if look else EVERYDAY, from_shot_id))
        self._resettle(approved)
        return self._restyled(character_id, before)

    def restyle_look(self, character_id: str, look_id: str, clothes: str) -> list[str]:
        """New clothes for a look (the user edited its description): its sheet is redrawn, its panels outdated."""
        before, approved = self._wearing(character_id), self.bible.is_approved
        self.bible.set_look(character_id, replace(self.bible.get(character_id).look(look_id), clothes=clothes.strip()))
        self._resettle(approved)
        return self._restyled(character_id, before)

    def drop_outfits_from(self, shot_ids: Iterable[str]) -> None:
        """Forget the outfit changes that start at these shots (their turn is being directed again)."""
        gone = set(shot_ids)
        self.outfits = [o for o in self.outfits if o.from_shot_id not in gone]
        self.settle_looks()

    def worn_looks(self) -> set[str]:
        """The looks some shot shows, as sheet targets ("wren/farmer_costume"). A look no shot shows (a costume
        the director replaced, or whose shots were deleted) is hidden and needs no sheet until it is worn again;
        a sheet it already has is kept for then."""
        return {
            sheet_target(cid, look.id)
            for s in self.shots
            for cid in s.character_ids
            if cid in self.bible and (look := self.look_in(s.id, cid)) is not None
        }

    def shown(self, character: Character) -> Character:
        """The character with only the looks some shot shows: what the cast tray lists."""
        worn = self.worn_looks()
        return replace(
            character, looks=tuple(lk for lk in character.looks if sheet_target(character.id, lk.id) in worn)
        )

    def approve_cast(self) -> None:
        self.bible.approve(unworn=self._unworn())

    def settle_looks(self) -> None:
        """An approved cast stays approved only while every look a shot shows has its sheet."""
        if self.bible.is_approved and any(
            look.reference is None
            for s in self.shots
            for cid in s.character_ids
            if cid in self.bible and (look := self.look_in(s.id, cid)) is not None
        ):
            self.bible.status = CastStatus.DRAFT

    def _resettle(self, approved: bool) -> None:
        """After an outfit change: a look no shot shows does not send an approved cast back to draft."""
        if approved and self.bible.status is CastStatus.DRAFT:
            self.bible.status = CastStatus.APPROVED
        self.settle_looks()

    def _unworn(self) -> set[str]:
        every = {sheet_target(c.id, lk.id) for c in self.bible.characters.values() for lk in c.looks}
        return every - self.worn_looks()

    def _wearing(self, character_id: str) -> dict[str, tuple[str, str]]:
        out = {}
        for s in self.shots:
            if character_id in s.character_ids:
                look = self.look_in(s.id, character_id)
                out[s.id] = (look.id, look.clothes) if look else (EVERYDAY, "")
        return out

    def _restyled(self, character_id: str, before: dict[str, tuple[str, str]]) -> list[str]:
        changed = [sid for sid, wore in self._wearing(character_id).items() if before.get(sid) != wore]
        self._mark_outdated(changed)
        return changed

    def _forget_outfits(self, character_id: str) -> None:
        self.outfits = [o for o in self.outfits if o.character_id != character_id]

    def _relocate_outfits(self, old_order: Sequence[str], fallback: str | None = None) -> None:
        """Outfit changes whose first shot is gone start at the next shot that is left (or `fallback`, the shot
        that took its place); with none after it, they are dropped."""
        present = {s.id for s in self.shots}
        moved = []
        for o in self.outfits:
            if o.from_shot_id in present:
                moved.append(o)
                continue
            after = old_order[old_order.index(o.from_shot_id) + 1 :] if o.from_shot_id in old_order else []
            target = fallback or next((sid for sid in after if sid in present), None)
            if target is not None:
                moved.append(replace(o, from_shot_id=target))
        self.outfits = moved
        self.settle_looks()

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
        old_order = [s.id for s in self.shots]
        kept = [s for s in self.shots if s.id not in old]
        ordered = [*kept[:at], *new, *kept[at:]]
        self.shots = [replace(s, number=n) for n, s in enumerate(ordered, start=1)]
        for shot_id in old:
            self.panels.pop(shot_id, None)
        self._relocate_outfits(old_order, new[0].id if new else None)
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

    def delete_shot(self, shot_id: str) -> None:
        """Delete one shot and its panel. Its words stay in the transcript, but the animatic skips its stretch of the
        recording: the other shots of its turn keep the voice they had."""
        shot = self.shot(shot_id)
        if len(shot.source_turn_ids) == 1:
            siblings = [s for s in self.shots if s.source_turn_ids == shot.source_turn_ids]
            starts = dict(zip((s.id for s in siblings), voice_offsets(siblings), strict=True))
            self.shots = [replace(s, voice_from_ms=starts[s.id]) if s.id in starts else s for s in self.shots]
        self._drop_shots([shot_id])

    def remove_turn(self, turn_id: str) -> list[str]:
        """Take a beat out of the story (a word said by mistake): its words, the shots made only from it and their
        panels. The animatic plays turns, so its stretch of the recording is no longer heard. A shot made from it
        and other turns keeps the others. Returns the removed shots' ids."""
        turn = self.turn(turn_id)
        sharing = [s for s in self.shots if turn_id in s.source_turn_ids]
        removed = [s.id for s in sharing if s.source_turn_ids == (turn_id,)]
        for i, s in enumerate(self.shots):
            if turn_id in s.source_turn_ids and s.id not in removed:
                rest = tuple(t for t in s.source_turn_ids if t != turn_id)
                shorter = max(1, s.duration_ms - turn.duration_ms // len(sharing))
                self.shots[i] = replace(s, source_turn_ids=rest, duration_ms=shorter)
        self.turns = [t for t in self.turns if t.id != turn_id]
        self._drop_shots(removed)
        return removed

    def merge_turns(self, first_id: str, second_id: str) -> TranscriptTurn:
        """Join two neighbouring beats of one recording (a sentence cut in two). The beat runs from the first's start
        to the second's end, and its shots share that time again by their words (ADR 0008)."""
        ids = [t.id for t in self.turns]
        first, second = self.turn(first_id), self.turn(second_id)
        if ids.index(second_id) != ids.index(first_id) + 1:
            raise InvalidValueError("only a beat and the one right after it can be merged")
        if session_of(first.id) != session_of(second.id) or first.episode != second.episode:
            raise InvalidValueError("only beats of the same recording and episode can be merged")
        direction = f"{first.for_director}\n\n{second.for_director}" if first.direction or second.direction else ""
        merged = replace(
            first,
            text=f"{first.text} {second.text}".strip(),
            end_ms=max(first.end_ms, second.end_ms),
            direction=direction,
        )
        self.turns = [merged if t.id == first.id else t for t in self.turns if t.id != second.id]
        for i, s in enumerate(self.shots):
            if second.id in s.source_turn_ids:
                sources = tuple(dict.fromkeys(first.id if t == second.id else t for t in s.source_turn_ids))
                self.shots[i] = replace(s, source_turn_ids=sources)
        own = [s for s in self.shots if s.source_turn_ids == (first.id,)]
        durations = split_duration(merged.duration_ms, [len(f"{s.action} {s.dialogue}".split()) for s in own])
        retimed = {s.id: d for s, d in zip(own, durations, strict=True)}
        self.shots = [
            replace(s, duration_ms=retimed[s.id], voice_from_ms=None) if s.id in retimed else s for s in self.shots
        ]
        return merged

    def _drop_shots(self, shot_ids: Sequence[str]) -> None:
        """Remove shots and their panels, renumber 1..n and move outfit changes that started at them."""
        gone = set(shot_ids)
        old_order = [s.id for s in self.shots]
        kept = [s for s in self.shots if s.id not in gone]
        self.shots = [replace(s, number=n) for n, s in enumerate(kept, start=1)]
        for shot_id in gone:
            self.panels.pop(shot_id, None)
        self._relocate_outfits(old_order)
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

    # ---- continuity supervisor (ADR 0012) ----

    def record_panel_review(self, shot_id: str, review: PanelReview) -> bool:
        """Keep a panel review; False if the panel has a newer render than the one reviewed."""
        return self.panel(shot_id).record_review(review)

    def accept_panel(self, shot_id: str) -> PanelReview:
        """The user saw the supervisor's issues and keeps the panel as it is."""
        panel = self.panel(shot_id)
        if panel.review is None or panel.review.outcome is not Outcome.NEEDS_USER:
            raise InvalidValueError(f"shot {shot_id}: nothing to accept")
        panel.review = replace(panel.review, outcome=Outcome.ACCEPTED)
        return panel.review

    def record_sheet_review(self, character_id: str, review: SheetReview) -> bool:
        """Keep a sheet review; False if the character has a different sheet now (or left the cast)."""
        if character_id not in self.bible or self.bible.get(character_id).reference != review.reference:
            return False
        self.sheet_reviews[character_id] = review
        return True

    def accept_sheet(self, character_id: str) -> SheetReview:
        review = self.sheet_reviews.get(character_id)
        if review is None or review.outcome is not Outcome.NEEDS_USER:
            raise InvalidValueError(f"{character_id}: nothing to accept")
        self.sheet_reviews[character_id] = replace(review, outcome=Outcome.ACCEPTED)
        return self.sheet_reviews[character_id]

    def log_supervisor(self, entry: SupervisorEntry) -> None:
        self.supervisor_log = [*self.supervisor_log, entry][-SUPERVISOR_LOG_SIZE:]
