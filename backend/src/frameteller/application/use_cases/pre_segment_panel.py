from __future__ import annotations

from frameteller.application import costs
from frameteller.application.jobs import compose_job
from frameteller.application.ports import BudgetGuard, JobQueuePort, ProjectRepository, SegmentationPort
from frameteller.application.prompts import concept_phrase
from frameteller.application.use_cases.compose_panel import layers_signature
from frameteller.domain import ObjectMask, Project


def character_mask_id(character_id: str) -> str:
    """Stable across revisions, so canvas transforms keep pointing at the right character."""
    return f"character:{character_id}"


class PreSegmentPanel:
    """Segment every character in a freshly rendered panel and cache the masks (ADR 0006)."""

    def __init__(
        self, repo: ProjectRepository, segmentation: SegmentationPort, budget: BudgetGuard, jobs: JobQueuePort
    ) -> None:
        self._repo, self._sam, self._budget, self._jobs = repo, segmentation, budget, jobs

    async def execute(self, project_id: str, shot_id: str, revision: int) -> list[ObjectMask]:
        snapshot = await self._repo.get(project_id)
        panel = snapshot.panel(shot_id)
        if panel.revision != revision:
            return []  # stale job: a newer revision exists and has its own job
        image_ref, _ = panel.require_ready()
        found = []
        for cid in snapshot.shot(shot_id).character_ids:
            mask_id = character_mask_id(cid)
            if mask_id in panel.masks:
                continue
            character = snapshot.bible.get(cid)
            await self._budget.charge(project_id, costs.SAM_IMAGE, f"pre-segment {shot_id} r{revision} {cid}")
            prefix = f"projects/{project_id}/panels/{shot_id}/r{revision}/masks/{cid}"
            segments = await self._sam.segment_concept(image_ref, concept_phrase(character), prefix)
            if segments:
                best = max(segments, key=lambda s: len(s.bitmap.data))
                found.append(ObjectMask(mask_id, character.name, best.bitmap, cutout=best.cutout, character_id=cid))

        def apply(project: Project) -> tuple[list[ObjectMask], str | None]:
            current = project.panel(shot_id)
            cached = [m for m in found if current.cache_mask(revision, m)]  # dropped if the panel moved on
            relayer = current.revision == revision and bool(current.layers()) and current.composite is None
            return cached, layers_signature(current) if relayer else None

        cached, signature = await self._repo.update(project_id, apply)
        if signature is not None:  # a new render of a panel with saved geometry: re-apply it (ADR 0005, 0010)
            await self._jobs.enqueue(compose_job(project_id, shot_id, revision, signature))
        return cached
