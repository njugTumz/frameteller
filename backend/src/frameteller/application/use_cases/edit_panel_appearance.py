from __future__ import annotations

from collections.abc import Sequence

from frameteller.application import costs
from frameteller.application.jobs import pre_segment_job
from frameteller.application.ports import (
    BudgetGuard,
    EditRequest,
    ImageGenerationPort,
    JobQueuePort,
    ProjectRepository,
    Quality,
)
from frameteller.application.prompts import edit_prompt
from frameteller.domain import MediaRef, Panel, Project


def reference_sheets(project: Project, shot_id: str) -> tuple[MediaRef, ...]:
    """The approved sheets of the shot's characters, so an edit redraws them as they were cast."""
    cast = project.cast_in(shot_id)  # in the looks they wear by this shot (ADR 0018)
    return tuple(c.reference for c in cast if c.reference)


class EditPanelAppearance:
    """Change how a selected object looks: a Muse Image edit of the stored render (ADR 0005, 0014). Not geometry."""

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
        image, _ = snapshot.panel(shot_id).require_ready()
        request = EditRequest(image, edit_prompt(change, target, parts), quality, reference_sheets(snapshot, shot_id))
        revision = snapshot.panel(shot_id).current_revision + 1
        await self._budget.charge(project_id, costs.IMAGE, f"edit {shot_id} r{revision}")
        stored = await self._images.edit(request, store_as=f"projects/{project_id}/panels/{shot_id}/r{revision}/image")

        def apply(project: Project) -> Panel:
            panel = project.panel(shot_id)
            panel.record_render(revision, stored.ref, stored.response_id, stored.size)  # refuses if overtaken
            return panel

        panel = await self._repo.update(project_id, apply)
        await self._jobs.enqueue(pre_segment_job(project_id, shot_id, panel.revision))
        return panel
