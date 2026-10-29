from __future__ import annotations

from frameteller.application.limits import VisitorAllowance
from frameteller.application.ports import IdGenerator, ProjectRepository
from frameteller.domain import PanelStyle, Project, Shot, UnknownShotError


class CreateProject:
    """Start a story. With an allowance, a visitor can start only so many a day (the public demo)."""

    def __init__(self, repo: ProjectRepository, ids: IdGenerator, visitors: VisitorAllowance | None = None) -> None:
        self._repo, self._ids, self._visitors = repo, ids, visitors

    async def execute(
        self, title: str = "", style: PanelStyle = PanelStyle.PENCIL, *, visitor: str | None = None
    ) -> Project:
        if self._visitors is not None and visitor is not None:
            await self._visitors.take(visitor)
        project = Project(id=self._ids.new_id(), title=title.strip(), style=style)
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
