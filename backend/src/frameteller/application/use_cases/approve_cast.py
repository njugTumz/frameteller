from __future__ import annotations

from frameteller.application.ports import ProjectRepository


class ApproveCast:
    """The user accepts every reference sheet; panels may now be drawn (ADR 0004)."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(self, project_id: str) -> None:
        project = await self._repo.get(project_id)
        project.bible.approve()
        await self._repo.save(project)
