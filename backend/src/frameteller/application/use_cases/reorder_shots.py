from __future__ import annotations

from collections.abc import Sequence

from frameteller.application.ports import ProjectRepository
from frameteller.domain import Shot


class ReorderShots:
    """Put shots in a new order ("swap shots 2 and 4"). Numbers stay 1..n."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(self, project_id: str, shot_ids: Sequence[str]) -> list[Shot]:
        project = await self._repo.get(project_id)
        project.reorder_shots(shot_ids)
        await self._repo.save(project)
        return list(project.shots)
