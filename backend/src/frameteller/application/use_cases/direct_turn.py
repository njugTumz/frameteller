from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from frameteller.application.ports import (
    DirectorPort,
    IdGenerator,
    LookChange,
    ProjectRepository,
    ShotDraft,
    ShotRevision,
)
from frameteller.domain import (
    EVERYDAY,
    Character,
    InvalidValueError,
    Look,
    Project,
    Shot,
    TranscriptTurn,
    sheet_target,
    split_duration,
)

REVEAL_WINDOW = 3  # a reveal may revise at most this many of the latest shots


@dataclass(frozen=True, slots=True)
class DirectedShots:
    shots: tuple[Shot, ...]
    new_characters: tuple[Character, ...]
    revised: tuple[Shot, ...] = ()  # earlier shots a reveal changed; their panels are outdated
    dropped_character_ids: tuple[str, ...] = ()  # guesses the reveal replaced, no longer in any shot
    capped: bool = False  # the episode reached its shot limit: shots past it were not added
    refusal: str = ""  # the director declined a real person or a copyrighted character, and says why
    new_looks: tuple[str, ...] = ()  # sheets to draw for new outfits, as "wren/farmer_costume" (ADR 0018)
    looks: dict[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)  # by shot id: who wears what


def shots_for_turn(drafts: Sequence[ShotDraft], turn: TranscriptTurn, ids: IdGenerator, first: int) -> list[Shot]:
    """Number the director's drafts from `first` and share the turn's time between them by word count (ADR 0008)."""
    words = [len(f"{d.action} {d.dialogue}".split()) for d in drafts]
    durations = split_duration(turn.duration_ms, words)
    return [
        Shot(
            id=ids.new_id(),
            number=first + i,
            framing=d.framing,
            character_ids=d.character_ids,
            setting=d.setting,
            action=d.action,
            dialogue=d.dialogue,
            source_turn_ids=d.source_turn_ids,
            duration_ms=durations[i],
            episode=turn.episode,
        )
        for i, d in enumerate(drafts)
    ]


def add_new_characters(project: Project, candidates: Sequence[Character]) -> tuple[Character, ...]:
    # Another turn may have introduced the same character meanwhile: the first description wins.
    new = tuple(c for c in candidates if c.id not in project.bible)
    for c in new:
        project.upsert_character(c)
    return new


def apply_revisions(project: Project, revisions: Sequence[ShotRevision]) -> tuple[list[Shot], list[str]]:
    """Revise the latest shots a reveal names ("something small and orange" was Pip), then drop guesses left unused.

    Only the last REVEAL_WINDOW shots can change; revisions of older shots are ignored.
    """
    window = {s.id for s in project.shots[-REVEAL_WINDOW:]}
    revised: list[Shot] = []
    before: set[str] = set()
    for r in revisions:
        if r.shot_id in window:
            before.update(project.shot(r.shot_id).character_ids)
            revised.append(project.revise_shot(r.shot_id, r.character_ids, r.action))
    return revised, project.drop_unused_characters(sorted(before))


def apply_looks(
    project: Project, changes: Sequence[LookChange], shot_at: Callable[[int], str | None]
) -> tuple[list[str], list[str]]:
    """Record outfit changes from the shot each starts at (ADR 0018). A look the character already has is worn as
    it is. Returns the sheets to draw ("wren/farmer_costume"), only of looks some shot shows, and the shots that
    now show other clothes. A change from a shot that was not added (the episode was full) or for an unknown
    character is skipped."""
    sheets, restyled = [], []
    for change in changes:
        shot_id = shot_at(change.from_shot)
        if shot_id is None or change.character_id not in project.bible:
            continue
        character = project.bible.get(change.character_id)
        look: Look | None = None
        if change.look_id != EVERYDAY:
            if character.has_look(change.look_id):
                look = character.look(change.look_id)
            else:
                try:
                    look = Look(change.look_id, change.label.strip(), change.clothes.strip())
                except InvalidValueError:
                    continue
        restyled += project.change_outfit(change.character_id, look, shot_id)
        if look is not None and project.bible.get(change.character_id).look(look.id).reference is None:
            sheets.append(sheet_target(change.character_id, look.id))
    worn = project.worn_looks()  # a look no shot shows (the director replaced it) is not drawn yet
    return [t for t in dict.fromkeys(sheets) if t in worn], list(dict.fromkeys(restyled))


def wearing(project: Project, shot_id: str) -> tuple[tuple[str, str], ...]:
    """Who in the shot is out of their everyday clothes, and in which look."""
    shot = project.shot(shot_id)
    return tuple((c, look.id) for c in shot.character_ids if (look := project.look_in(shot_id, c)) is not None)


class DirectTurn:
    """Direct one finished transcript turn into shots (ADR 0002), revising earlier shots a reveal explains."""

    def __init__(
        self,
        repo: ProjectRepository,
        director: DirectorPort,
        ids: IdGenerator,
        *,
        max_shots_per_episode: int | None = None,
    ) -> None:
        self._repo, self._director, self._ids, self._max_shots = repo, director, ids, max_shots_per_episode

    async def execute(self, project_id: str, turn: TranscriptTurn) -> DirectedShots:
        snapshot = await self._repo.get(project_id)
        snapshot.add_turn(turn)
        directed = await self._director.direct_turn(turn, snapshot)

        def apply(project: Project) -> DirectedShots:
            project.add_turn(turn)
            new = add_new_characters(project, directed.new_characters)
            revised, dropped = apply_revisions(project, directed.revisions)
            drafts = list(directed.shots)
            in_episode = sum(s.episode == turn.episode for s in project.shots)
            room = len(drafts) if self._max_shots is None else max(0, self._max_shots - in_episode)
            shots = shots_for_turn(drafts[:room], turn, self._ids, len(project.shots) + 1) if room else []
            project.append_shots(shots)
            capped = len(drafts) > room
            oldest = len(project.shots) - len(shots) - REVEAL_WINDOW  # a change may start in the reveal window

            def shot_at(number: int) -> str | None:
                return project.shots[number - 1].id if oldest < number <= len(project.shots) else None

            sheets, restyled = apply_looks(project, directed.looks, shot_at)
            new_ids = {s.id for s in shots}
            for shot_id in restyled:
                if shot_id not in new_ids and all(r.id != shot_id for r in revised):
                    revised.append(project.shot(shot_id))
            return DirectedShots(
                tuple(shots),
                new,
                tuple(revised),
                tuple(dropped),
                capped,
                directed.refusal,
                tuple(sheets),
                {s.id: wearing(project, s.id) for s in [*shots, *revised]},
            )

        return await self._repo.update(project_id, apply)
