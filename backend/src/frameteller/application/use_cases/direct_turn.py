from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from frameteller.application.ports import DirectorPort, IdGenerator, ProjectRepository, ShotDraft
from frameteller.domain import Character, Project, Shot, TranscriptTurn, split_duration


@dataclass(frozen=True, slots=True)
class DirectedShots:
    shots: tuple[Shot, ...]
    new_characters: tuple[Character, ...]


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


class DirectTurn:
    """Direct one finished transcript turn into shots (ADR 0002)."""

    def __init__(self, repo: ProjectRepository, director: DirectorPort, ids: IdGenerator) -> None:
        self._repo, self._director, self._ids = repo, director, ids

    async def execute(self, project_id: str, turn: TranscriptTurn) -> DirectedShots:
        snapshot = await self._repo.get(project_id)
        snapshot.add_turn(turn)
        directed = await self._director.direct_turn(turn, snapshot)

        def apply(project: Project) -> DirectedShots:
            project.add_turn(turn)
            new = add_new_characters(project, directed.new_characters)
            shots = shots_for_turn(directed.shots, turn, self._ids, len(project.shots) + 1)
            project.append_shots(shots)
            return DirectedShots(tuple(shots), new)

        return await self._repo.update(project_id, apply)
