from __future__ import annotations

from frameteller.application.ports import ProjectRepository
from frameteller.domain import CanvasTransform, Project


class MovePanelObject:
    """Move, resize or delete a selected object on our canvas. No model call (ADR 0005)."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        project_id: str,
        shot_id: str,
        object_id: str,
        *,
        dx: int = 0,
        dy: int = 0,
        scale: float = 1.0,
        deleted: bool = False,
    ) -> CanvasTransform:
        transform = CanvasTransform(object_id, dx, dy, scale, deleted)

        def apply(project: Project) -> CanvasTransform:
            panel = project.panel(shot_id)
            panel.require_ready()
            panel.transform(transform)
            return transform

        return await self._repo.update(project_id, apply)
