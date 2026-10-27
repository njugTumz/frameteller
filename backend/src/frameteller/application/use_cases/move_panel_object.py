from __future__ import annotations

from frameteller.application.ports import ProjectRepository
from frameteller.domain import CanvasTransform


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
        project = await self._repo.get(project_id)
        panel = project.panel(shot_id)
        panel.require_ready()
        transform = CanvasTransform(object_id, dx, dy, scale, deleted)
        panel.transform(transform)
        await self._repo.save(project)
        return transform
