from __future__ import annotations

import logging

from frameteller.application import costs
from frameteller.application.errors import ApplicationError, ModelContentFilteredError
from frameteller.application.image_safety import suggest_change
from frameteller.application.jobs import pre_segment_job, supervise_job
from frameteller.application.ports import (
    BudgetGuard,
    ImageGenerationPort,
    ImageRequest,
    JobQueuePort,
    ProjectRepository,
    Quality,
)
from frameteller.application.prompts import Redraw, panel_prompt
from frameteller.domain import Panel, Project

log = logging.getLogger("frameteller.panels")


class PanelRefusedError(ApplicationError):
    """Muse Image refused the frame twice. The message says what to change; the panel keeps a suggestion."""

    user_message = (
        "Muse Image's safety filter turned this frame down twice. Redraw it and say plainly what happens, "
        "by look and action, or use the suggested change."
    )


class GeneratePanel:
    """Draw revision `revision` of a shot's panel from the approved cast's reference sheets.

    Idempotent on (project, shot, revision): if that revision is already rendered, nothing is charged
    and the image port is not called.
    """

    def __init__(
        self,
        repo: ProjectRepository,
        images: ImageGenerationPort,
        budget: BudgetGuard,
        jobs: JobQueuePort,
    ) -> None:
        self._repo, self._images, self._budget, self._jobs = repo, images, budget, jobs

    async def execute(
        self, project_id: str, shot_id: str, revision: int, quality: Quality = "low", redraw: Redraw | None = None
    ) -> Panel:
        """`redraw`: the user's Redraw, which varies the composition and applies what should change (ADR 0022)."""
        snapshot = await self._repo.get(project_id)
        snapshot.require_cast_approved()
        shot = snapshot.shot(shot_id)
        panel = snapshot.panel(shot_id)
        if panel.has_render(revision):
            return panel

        cast = snapshot.cast_in(shot_id)  # each in the look they wear by this shot (ADR 0018)
        references = tuple(c.reference for c in cast if c.reference is not None)
        await self._budget.charge(project_id, costs.IMAGE, f"panel {shot_id} r{revision}")
        try:
            stored = await self._images.generate(
                ImageRequest(
                    panel_prompt(shot, cast, snapshot.style, redraw=redraw, revision=revision),
                    quality,
                    "panel",
                    references,
                    fallback_prompt=panel_prompt(
                        shot, cast, snapshot.style, safer=True, redraw=redraw, revision=revision
                    ),
                ),
                store_as=f"projects/{project_id}/panels/{shot_id}/r{revision}/image",
            )
        except ModelContentFilteredError as e:
            suggestion = suggest_change(shot.action)
            await self._repo.update(project_id, lambda p: p.panel(shot_id).mark_failed(suggestion))
            log.warning("panel refused twice by the content filter", extra={"shot_id": shot_id})
            raise PanelRefusedError(str(e)) from e
        except Exception:
            await self._repo.update(project_id, lambda p: p.panel(shot_id).mark_failed())
            raise

        def apply(project: Project) -> tuple[Panel, bool]:
            current = project.panel(shot_id)
            if current.has_render(revision):
                return current, False  # a concurrent run of the same revision won
            current.record_render(revision, stored.ref, stored.response_id, stored.size)
            return current, True

        rendered, recorded = await self._repo.update(project_id, apply)
        if recorded:
            await self._jobs.enqueue(pre_segment_job(project_id, shot_id, rendered.revision))
            if snapshot.continuity_checks:  # reviewed in the background; drawing never waits for it
                await self._jobs.enqueue(supervise_job(project_id, shot_id, rendered.revision, quality))
        return rendered
