from __future__ import annotations

from collections.abc import Sequence

from frameteller.application import costs
from frameteller.application.jobs import pre_segment_job
from frameteller.application.ports import (
    BudgetGuard,
    ImageGenerationPort,
    JobQueuePort,
    MediaStoragePort,
    ProjectRepository,
)
from frameteller.application.prompts import PANEL_SIZE, edit_prompt
from frameteller.domain import Panel


class EditPanelAppearance:
    """Change how a selected object looks with a chained Muse Image edit (ADR 0005). Never geometry."""

    def __init__(
        self,
        repo: ProjectRepository,
        images: ImageGenerationPort,
        storage: MediaStoragePort,
        budget: BudgetGuard,
        jobs: JobQueuePort,
    ) -> None:
        self._repo, self._images, self._storage = repo, images, storage
        self._budget, self._jobs = budget, jobs

    async def execute(
        self, project_id: str, shot_id: str, target: str, parts: Sequence[str], change: str, quality: str = "high"
    ) -> Panel:
        project = await self._repo.get(project_id)
        project.require_cast_approved()
        panel = project.panel(shot_id)
        _, response_id = panel.require_ready()
        prompt = edit_prompt(change, target, parts)
        revision = panel.revision + 1
        await self._budget.charge(project_id, costs.IMAGE, f"edit {shot_id} r{revision}")
        image = await self._images.edit(response_id, prompt, PANEL_SIZE, quality)
        ref = await self._storage.put(
            f"projects/{project_id}/panels/{shot_id}/r{revision}", image.data, image.content_type
        )
        panel.record_render(revision, ref, image.response_id)
        await self._repo.save(project)
        await self._jobs.enqueue(pre_segment_job(project_id, shot_id, revision))
        return panel
