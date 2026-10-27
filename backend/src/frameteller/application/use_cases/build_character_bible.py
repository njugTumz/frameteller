from __future__ import annotations

from frameteller.application.ports import DirectorPort, ProjectRepository
from frameteller.domain import CharacterBible, Project


class BuildCharacterBible:
    """Ask the director for one canonical description per character in the transcript so far."""

    def __init__(self, repo: ProjectRepository, director: DirectorPort) -> None:
        self._repo, self._director = repo, director

    async def execute(self, project_id: str) -> CharacterBible:
        snapshot = await self._repo.get(project_id)
        found = await self._director.extract_characters(snapshot.turns, list(snapshot.bible.characters.values()))

        def apply(project: Project) -> CharacterBible:
            for c in found:
                if c.id not in project.bible:
                    project.upsert_character(c)
            return project.bible

        return await self._repo.update(project_id, apply)
