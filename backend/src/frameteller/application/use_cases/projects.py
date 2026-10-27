from __future__ import annotations

from frameteller.application.ports import IdGenerator, ProjectRepository
from frameteller.domain import Project, Shot, UnknownShotError


class CreateProject:
    def __init__(self, repo: ProjectRepository, ids: IdGenerator) -> None:
        self._repo, self._ids = repo, ids

    async def execute(self, title: str = "") -> Project:
        project = Project(id=self._ids.new_id(), title=title.strip())
        await self._repo.save(project)
        return project


class GetProject:
    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(self, project_id: str) -> Project:
        return await self._repo.get(project_id)


class FindShot:
    """Shots are addressed by their number in the UI and by voice ("shot 3"); use cases take ids."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(self, project_id: str, number: int) -> Shot:
        for shot in (await self._repo.get(project_id)).shots:
            if shot.number == number:
                return shot
        raise UnknownShotError(f"no shot number {number}")
