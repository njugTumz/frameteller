from __future__ import annotations

from frameteller.application import costs
from frameteller.application.ports import BudgetGuard, ProjectRepository, SegmentationPort
from frameteller.domain import ObjectMask, Project


def character_mask_id(character_id: str) -> str:
    """Stable across revisions, so canvas transforms keep pointing at the right character."""
    return f"character:{character_id}"


class PreSegmentPanel:
    """Segment every character in a freshly rendered panel and cache the masks (ADR 0006)."""

    def __init__(self, repo: ProjectRepository, segmentation: SegmentationPort, budget: BudgetGuard) -> None:
        self._repo, self._sam, self._budget = repo, segmentation, budget

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
            segments = await self._sam.segment_concept(image_ref, character.name, prefix)
            if segments:
                best = max(segments, key=lambda s: len(s.bitmap.data))
                found.append(ObjectMask(mask_id, character.name, best.bitmap, cutout=best.cutout, character_id=cid))

        def apply(project: Project) -> list[ObjectMask]:
            current = project.panel(shot_id)
            return [m for m in found if current.cache_mask(revision, m)]  # dropped if the panel moved on

        return await self._repo.update(project_id, apply)
