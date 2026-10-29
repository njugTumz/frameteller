"""Saved geometry: move or resize a selected object, then composite it on a clean plate (ADR 0010)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence

from frameteller.application import costs
from frameteller.application.ports import (
    BudgetGuard,
    CompositorPort,
    CutoutLayer,
    EditRequest,
    ImageGenerationPort,
    MediaStoragePort,
    ProjectRepository,
)
from frameteller.application.prompts import clean_plate_prompt, concept_phrase
from frameteller.domain import CleanPlate, Composite, Panel, Project, plate_key


def layers_signature(panel: Panel) -> str:
    """The arrangement to compose: base, every layer, and the revision shown now.

    The shown revision makes moving back to an earlier arrangement a new job instead of a finished duplicate.
    """
    rows = [f"{t.object_id}:{t.dx}:{t.dy}:{t.scale}:{t.deleted}" for t in sorted(panel.transforms, key=str)]
    return f"r{panel.revision}|c{panel.current_revision}|" + "|".join(rows)


class ComposePanel:
    """Background job: clean plate without the moved objects, then their cut-outs at their new place.

    The plate comes from Muse Image edits of our stored images that each remove one object (ADR 0014), cached
    per base revision, so
    moving the same object again costs nothing and moving a second one costs one more edit. Pasting is ours.
    """

    def __init__(
        self,
        repo: ProjectRepository,
        images: ImageGenerationPort,
        storage: MediaStoragePort,
        compositor: CompositorPort,
        budget: BudgetGuard,
    ) -> None:
        self._repo, self._images, self._storage = repo, images, storage
        self._compositor, self._budget = compositor, budget

    async def execute(self, project_id: str, shot_id: str, base_revision: int) -> Composite | None:
        snapshot = await self._repo.get(project_id)
        panel = snapshot.panel(shot_id)
        if panel.revision != base_revision:
            return None  # a newer render replaced the base; its own pre-segmentation queues a composite
        panel.require_ready()
        layers = panel.layers()
        if not layers:
            await self._repo.update(project_id, lambda p: p.panel(shot_id).clear_composite())
            return None
        plate = await self._plate(snapshot, panel, [m.id for m, _ in layers])
        cutouts = []
        for mask, t in layers:
            if not t.deleted and mask.cutout is not None:
                image = await self._storage.get(mask.cutout)
                cutouts.append(CutoutLayer(image, mask.box.left + t.dx, mask.box.top + t.dy, t.scale))
        size = panel.size
        assert size is not None  # a ready panel has a size
        data = await self._compositor.compose(await self._storage.get(plate.image), cutouts, size)
        digest = hashlib.sha256(layers_signature(panel).encode()).hexdigest()[:12]
        ref = await self._storage.put(
            f"projects/{project_id}/panels/{shot_id}/r{base_revision}/composites/{digest}.webp", data, "image/webp"
        )
        return await self._repo.update(
            project_id, lambda p: p.panel(shot_id).record_composite(base_revision, ref, size)
        )

    async def _plate(self, project: Project, panel: Panel, object_ids: Sequence[str]) -> CleanPlate:
        wanted = plate_key(object_ids)
        if wanted in panel.plates:
            return panel.plates[wanted]
        # Start from the biggest cached plate that removes only objects we want removed.
        start = max(
            (p for p in panel.plates.values() if set(p.object_ids) <= set(object_ids)),
            key=lambda p: len(p.object_ids),
            default=None,
        )
        removed = list(start.object_ids) if start else []
        source = start.image if start else panel.require_ready()[0]
        plate = start
        for object_id in sorted(set(object_ids) - set(removed)):
            removed.append(object_id)
            key = plate_key(removed)
            name = hashlib.sha256(key.encode()).hexdigest()[:12]
            await self._budget.charge(project.id, costs.IMAGE, f"clean plate {panel.shot_id} r{panel.revision}")
            request = EditRequest(source, clean_plate_prompt(self._noun_phrase(project, panel, object_id)), "high")
            stored = await self._images.edit(
                request, store_as=f"projects/{project.id}/panels/{panel.shot_id}/r{panel.revision}/plates/{name}"
            )
            plate = CleanPlate(tuple(sorted(removed)), stored.ref, stored.response_id)
            source = stored.ref
            await self._repo.update(project.id, _cache(panel.shot_id, panel.revision, plate))
        assert plate is not None
        return plate

    @staticmethod
    def _noun_phrase(project: Project, panel: Panel, object_id: str) -> str:
        """What to remove, as the image model will recognise it: a visual phrase, not a character's name."""
        mask = panel.masks[object_id]
        if mask.character_id and mask.character_id in project.bible:
            return concept_phrase(project.bible.get(mask.character_id))
        return mask.label


def _cache(shot_id: str, revision: int, plate: CleanPlate) -> Callable[[Project], bool]:
    return lambda p: p.panel(shot_id).cache_plate(revision, plate)
