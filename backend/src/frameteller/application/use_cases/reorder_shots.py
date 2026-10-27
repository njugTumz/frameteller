from __future__ import annotations

from collections.abc import Sequence

from frameteller.application.ports import ProjectRepository
from frameteller.domain import Project, Shot


class ReorderShots:
    """Put shots in a new order ("swap shots 2 and 4"). Numbers stay 1..n."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(self, project_id: str, shot_ids: Sequence[str]) -> list[Shot]:
        def apply(project: Project) -> list[Shot]:
            project.reorder_shots(shot_ids)
            return list(project.shots)

        return await self._repo.update(project_id, apply)
