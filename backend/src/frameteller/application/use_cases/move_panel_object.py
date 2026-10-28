from __future__ import annotations

from frameteller.application.jobs import compose_job
from frameteller.application.ports import JobQueuePort, ProjectRepository
from frameteller.application.use_cases.compose_panel import layers_signature
from frameteller.application.use_cases.requests import JobTicket
from frameteller.domain import CanvasTransform, Project


class MovePanelObject:
    """Move, resize or delete a selected object, saved as a layer on the panel (ADR 0005, 0010).

    No model call here: the composite job makes a clean plate the first time an object moves.
    """

    def __init__(self, repo: ProjectRepository, jobs: JobQueuePort) -> None:
        self._repo, self._jobs = repo, jobs

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
    ) -> JobTicket:
        transform = CanvasTransform(object_id, dx, dy, scale, deleted)

        def apply(project: Project) -> tuple[int, str]:
            panel = project.panel(shot_id)
            panel.require_ready()
            panel.transform(transform)
            return panel.revision, layers_signature(panel)

        base, signature = await self._repo.update(project_id, apply)
        job = compose_job(project_id, shot_id, base, signature)
        return JobTicket.of(job, await self._jobs.enqueue(job))
