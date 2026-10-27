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
from frameteller.domain import Panel, Project


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
        snapshot = await self._repo.get(project_id)
        snapshot.require_cast_approved()
        _, response_id = snapshot.panel(shot_id).require_ready()
        prompt = edit_prompt(change, target, parts)
        revision = snapshot.panel(shot_id).revision + 1
        await self._budget.charge(project_id, costs.IMAGE, f"edit {shot_id} r{revision}")
        stored = await self._images.edit(
            response_id, prompt, quality, store_as=f"projects/{project_id}/panels/{shot_id}/r{revision}"
        )

        def apply(project: Project) -> Panel:
            panel = project.panel(shot_id)
            panel.record_render(revision, stored.ref, stored.response_id, stored.size)  # refuses if overtaken
            return panel

        panel = await self._repo.update(project_id, apply)
        await self._jobs.enqueue(pre_segment_job(project_id, shot_id, revision))
        return panel
