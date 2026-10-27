from __future__ import annotations

from frameteller.application.ports import DirectorPort, IdGenerator, ProjectRepository
from frameteller.domain import Shot, TranscriptTurn


class DirectTurn:
    """Direct one finished transcript turn into shots (ADR 0002)."""

    def __init__(self, repo: ProjectRepository, director: DirectorPort, ids: IdGenerator) -> None:
        self._repo, self._director, self._ids = repo, director, ids

    async def execute(self, project_id: str, turn: TranscriptTurn) -> list[Shot]:
        project = await self._repo.get(project_id)
        project.add_turn(turn)
        directed = await self._director.direct_turn(turn, project)
        for c in directed.new_characters:
            project.upsert_character(c)
        first = len(project.shots) + 1
        shots = [
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
        ]
        project.append_shots(shots)
        await self._repo.save(project)
        return shots
