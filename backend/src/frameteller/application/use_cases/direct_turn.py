from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from frameteller.application.ports import DirectorPort, IdGenerator, ProjectRepository, ShotDraft, ShotRevision
from frameteller.domain import Character, Project, Shot, TranscriptTurn, split_duration

REVEAL_WINDOW = 3  # a reveal may revise at most this many of the latest shots


@dataclass(frozen=True, slots=True)
class DirectedShots:
    shots: tuple[Shot, ...]
    new_characters: tuple[Character, ...]
    revised: tuple[Shot, ...] = ()  # earlier shots a reveal changed; their panels are outdated
    dropped_character_ids: tuple[str, ...] = ()  # guesses the reveal replaced, no longer in any shot


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


class DirectTurn:
    """Direct one finished transcript turn into shots (ADR 0002), revising earlier shots a reveal explains."""

    def __init__(self, repo: ProjectRepository, director: DirectorPort, ids: IdGenerator) -> None:
        self._repo, self._director, self._ids = repo, director, ids

    async def execute(self, project_id: str, turn: TranscriptTurn) -> DirectedShots:
        snapshot = await self._repo.get(project_id)
        snapshot.add_turn(turn)
        directed = await self._director.direct_turn(turn, snapshot)

        def apply(project: Project) -> DirectedShots:
            project.add_turn(turn)
            new = add_new_characters(project, directed.new_characters)
            revised, dropped = apply_revisions(project, directed.revisions)
            shots = shots_for_turn(directed.shots, turn, self._ids, len(project.shots) + 1)
            project.append_shots(shots)
            return DirectedShots(tuple(shots), new, tuple(revised), tuple(dropped))

        return await self._repo.update(project_id, apply)
