from __future__ import annotations

from frameteller.application.ports import DirectorPort, ProjectRepository
from frameteller.domain import CharacterBible


class BuildCharacterBible:
    """Ask the director for one canonical description per character in the transcript so far."""

    def __init__(self, repo: ProjectRepository, director: DirectorPort) -> None:
        self._repo, self._director = repo, director

    async def execute(self, project_id: str) -> CharacterBible:
        project = await self._repo.get(project_id)
        known = list(project.bible.characters.values())
        for c in await self._director.extract_characters(project.turns, known):
            project.upsert_character(c)
        await self._repo.save(project)
        return project.bible
