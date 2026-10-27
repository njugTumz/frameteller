from __future__ import annotations

from frameteller.application import costs
from frameteller.application.errors import NothingToSegmentError
from frameteller.application.ports import (
    BudgetGuard,
    IdGenerator,
    MediaStoragePort,
    ProjectRepository,
    SegmentationPort,
)
from frameteller.domain import ObjectMask, Point


class SegmentObjectAtPoint:
    """Select the object under a click. A cached mask that contains the point is returned without calling SAM."""

    def __init__(
        self,
        repo: ProjectRepository,
        storage: MediaStoragePort,
        segmentation: SegmentationPort,
        budget: BudgetGuard,
        ids: IdGenerator,
    ) -> None:
        self._repo, self._storage, self._sam = repo, storage, segmentation
        self._budget, self._ids = budget, ids

    async def execute(self, project_id: str, shot_id: str, point: Point) -> ObjectMask:
        project = await self._repo.get(project_id)
        panel = project.panel(shot_id)
        image_ref, _ = panel.require_ready()
        if hit := panel.mask_at(point):
            return hit
        await self._budget.charge(project_id, costs.SAM_IMAGE, f"click {shot_id} r{panel.revision}")
        segment = await self._sam.segment_point(await self._storage.get(image_ref), point)
        if segment is None:
            raise NothingToSegmentError(f"nothing found at ({point.x}, {point.y})")
        mask = ObjectMask(id=f"object:{self._ids.new_id()}", label=segment.label or "object", bitmap=segment.bitmap)
        panel.cache_mask(panel.revision, mask)
        await self._repo.save(project)
        return mask
