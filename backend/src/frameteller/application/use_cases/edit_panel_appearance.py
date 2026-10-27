from __future__ import annotations

from collections.abc import Sequence

from frameteller.application import costs
from frameteller.application.jobs import pre_segment_job
from frameteller.application.ports import (
    BudgetGuard,
    ImageGenerationPort,
    JobQueuePort,
    ProjectRepository,
    Quality,
)
from frameteller.application.prompts import edit_prompt
from frameteller.domain import Panel


class EditPanelAppearance:
    """Change how a selected object looks with a chained Muse Image edit (ADR 0005). Never geometry."""

    def __init__(
        self,
        repo: ProjectRepository,
        images: ImageGenerationPort,
        budget: BudgetGuard,
        jobs: JobQueuePort,
    ) -> None:
        self._repo, self._images, self._budget, self._jobs = repo, images, budget, jobs

    async def execute(
        self, project_id: str, shot_id: str, target: str, parts: Sequence[str], change: str, quality: Quality = "high"
    ) -> Panel:
        project = await self._repo.get(project_id)
        project.require_cast_approved()
        panel = project.panel(shot_id)
        _, response_id = panel.require_ready()
        prompt = edit_prompt(change, target, parts)
        revision = panel.revision + 1
        await self._budget.charge(project_id, costs.IMAGE, f"edit {shot_id} r{revision}")
        stored = await self._images.edit(
            response_id, prompt, quality, store_as=f"projects/{project_id}/panels/{shot_id}/r{revision}"
        )
        panel.record_render(revision, stored.ref, stored.response_id, stored.size)
        await self._repo.save(project)
        await self._jobs.enqueue(pre_segment_job(project_id, shot_id, revision))
        return panel
