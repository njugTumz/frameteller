from __future__ import annotations

from frameteller.application import costs
from frameteller.application.ports import BudgetGuard, MediaStoragePort, ProjectRepository, SegmentationPort
from frameteller.domain import ObjectMask


def character_mask_id(character_id: str) -> str:
    """Stable across revisions, so canvas transforms keep pointing at the right character."""
    return f"character:{character_id}"


class PreSegmentPanel:
    """Segment every character in a freshly rendered panel and cache the masks (ADR 0006)."""

    def __init__(
        self, repo: ProjectRepository, storage: MediaStoragePort, segmentation: SegmentationPort, budget: BudgetGuard
    ) -> None:
        self._repo, self._storage, self._sam, self._budget = repo, storage, segmentation, budget

    async def execute(self, project_id: str, shot_id: str, revision: int) -> list[ObjectMask]:
        project = await self._repo.get(project_id)
        panel = project.panel(shot_id)
        if panel.revision != revision:
            return []  # stale job: a newer revision exists and has its own job
        image_ref, _ = panel.require_ready()
        image = await self._storage.get(image_ref)
        cached = []
        for cid in project.shot(shot_id).character_ids:
            mask_id = character_mask_id(cid)
            if mask_id in panel.masks:
                continue
            character = project.bible.get(cid)
            await self._budget.charge(project_id, costs.SAM_IMAGE, f"pre-segment {shot_id} r{revision} {cid}")
            segments = await self._sam.segment_concept(image, character.name)
            if not segments:
                continue
            best = max(segments, key=lambda s: len(s.bitmap.data))
            mask = ObjectMask(id=mask_id, label=character.name, bitmap=best.bitmap, character_id=cid)
            if panel.cache_mask(revision, mask):
                cached.append(mask)
        await self._repo.save(project)
        return cached
