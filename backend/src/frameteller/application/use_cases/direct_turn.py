from __future__ import annotations

from dataclasses import dataclass

from frameteller.application.ports import DirectorPort, IdGenerator, ProjectRepository
from frameteller.domain import Character, Project, Shot, TranscriptTurn


@dataclass(frozen=True, slots=True)
class DirectedShots:
    shots: tuple[Shot, ...]
    new_characters: tuple[Character, ...]


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
            # Another turn may have introduced the same character meanwhile: the first description wins.
            new = tuple(c for c in directed.new_characters if c.id not in project.bible)
            for c in new:
                project.upsert_character(c)
            first = len(project.shots) + 1
            shots = tuple(
                Shot(
                    id=self._ids.new_id(),
                    number=first + i,
                    framing=d.framing,
                    character_ids=d.character_ids,
                    setting=d.setting,
                    action=d.action,
                    dialogue=d.dialogue,
                    source_turn_ids=d.source_turn_ids,
                    duration_ms=d.duration_ms,
                )
                for i, d in enumerate(directed.shots)
            )
            project.append_shots(shots)
            return DirectedShots(shots, new)

        return await self._repo.update(project_id, apply)
