from __future__ import annotations

from frameteller.application import costs
from frameteller.application.errors import NothingToSegmentError
from frameteller.application.ports import (
    BudgetGuard,
    IdGenerator,
    ProjectRepository,
    SegmentationPort,
)
from frameteller.domain import ObjectMask, Point, Size


class SegmentObjectAtPoint:
    """Select the object under a click. A cached mask that contains the point is returned without calling SAM."""

    def __init__(
        self,
        repo: ProjectRepository,
        segmentation: SegmentationPort,
        budget: BudgetGuard,
        ids: IdGenerator,
    ) -> None:
        self._repo, self._sam, self._budget, self._ids = repo, segmentation, budget, ids

    async def execute(self, project_id: str, shot_id: str, click: Point, shown: Size | None = None) -> ObjectMask:
        """`click` is in the coordinates of a preview of size `shown`, or in media pixels if `shown` is None."""
        project = await self._repo.get(project_id)
        panel = project.panel(shot_id)
        image_ref, _ = panel.require_ready()
        point = click.to_media(shown, panel.size) if shown and panel.size else click
        if hit := panel.mask_at(point):
            return hit
        await self._budget.charge(project_id, costs.SAM_IMAGE, f"click {shot_id} r{panel.revision}")
        object_id = f"object:{self._ids.new_id()}"
        prefix = f"projects/{project_id}/panels/{shot_id}/r{panel.revision}/masks/{object_id}"
        segment = await self._sam.segment_point(image_ref, point, prefix)
        if segment is None:
            raise NothingToSegmentError(f"nothing found at ({point.x}, {point.y})")
        mask = ObjectMask(object_id, segment.label or "object", segment.bitmap, cutout=segment.mask_ref)
        panel.cache_mask(panel.revision, mask)
        await self._repo.save(project)
        return mask
