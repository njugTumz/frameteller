"""Panels, their revisions, cached object masks and canvas operations (ADR 0005, 0006)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from enum import StrEnum

from frameteller.domain.errors import (
    InvalidValueError,
    PanelNotReadyError,
    RevisionOrderError,
    UnknownObjectError,
)
from frameteller.domain.media import MediaRef
from frameteller.domain.review import PanelReview


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int

    def to_media(self, shown: Size, media: Size, offset: Point | None = None) -> Point:
        """Convert a click on a scaled preview to media pixels: subtract the offset, scale, round down, clamp."""
        ox, oy = (offset.x, offset.y) if offset else (0, 0)
        x = (self.x - ox) * media.width // shown.width
        y = (self.y - oy) * media.height // shown.height
        return Point(max(0, min(media.width - 1, x)), max(0, min(media.height - 1, y)))


@dataclass(frozen=True, slots=True)
class Size:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise InvalidValueError(f"invalid size {self.width}x{self.height}")


@dataclass(frozen=True, slots=True)
class Box:
    """Pixel box, half-open on the right and bottom like SAM's parsed records."""

    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if self.left < 0 or self.top < 0 or self.right <= self.left or self.bottom <= self.top:
            raise InvalidValueError(f"invalid box {self}")

    def contains(self, p: Point) -> bool:
        return self.left <= p.x < self.right and self.top <= p.y < self.bottom

    @property
    def centre(self) -> Point:
        return Point((self.left + self.right) // 2, (self.top + self.bottom) // 2)


@dataclass(frozen=True, slots=True)
class MaskBitmap:
    """Row-major 0/1 raster covering `box`, as decoded from SAM."""

    box: Box
    data: bytes

    def __post_init__(self) -> None:
        w, h = self.box.right - self.box.left, self.box.bottom - self.box.top
        if len(self.data) != w * h:
            raise InvalidValueError(f"mask raster has {len(self.data)} cells, box needs {w * h}")

    def contains(self, p: Point) -> bool:
        if not self.box.contains(p):
            return False
        width = self.box.right - self.box.left
        return self.data[(p.y - self.box.top) * width + (p.x - self.box.left)] == 1


@dataclass(frozen=True, slots=True)
class ObjectMask:
    id: str
    label: str
    bitmap: MaskBitmap
    cutout: MediaRef | None = None
    character_id: str | None = None

    @property
    def box(self) -> Box:
        return self.bitmap.box


@dataclass(frozen=True, slots=True)
class CanvasTransform:
    """Geometry applied on our canvas to a SAM cut-out, never by the image model (ADR 0005)."""

    object_id: str
    dx: int = 0
    dy: int = 0
    scale: float = 1.0
    deleted: bool = False

    def __post_init__(self) -> None:
        if self.scale <= 0:
            raise InvalidValueError("scale must be positive")

    @property
    def is_identity(self) -> bool:
        return not self.deleted and self.dx == 0 and self.dy == 0 and self.scale == 1.0


@dataclass(frozen=True, slots=True)
class CleanPlate:
    """The base render with some objects removed by the image model, so moved cut-outs leave no ghost (ADR 0010)."""

    object_ids: tuple[str, ...]  # sorted
    image: MediaRef
    response_id: str  # recorded for tracing; the next removal edits `image`, never a chain (ADR 0014)

    @property
    def key(self) -> str:
        return plate_key(self.object_ids)


def plate_key(object_ids: Iterable[str]) -> str:
    return "+".join(sorted(set(object_ids)))


@dataclass(frozen=True, slots=True)
class Composite:
    """The base render with its geometry layers applied: what the storyboard, animatic and shares show."""

    revision: int
    image: MediaRef
    size: Size


@dataclass(frozen=True, slots=True)
class PanelVersion:
    """An earlier drawing of a panel, as it was shown, kept so a redraw can be undone ("Keep previous")."""

    revision: int
    image: MediaRef
    size: Size
    response_id: str
    review: PanelReview | None = None  # the supervisor's word on it, restored with it


KEEP_VERSIONS = 6  # earlier drawings kept per panel; the oldest is forgotten first


class PanelStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


@dataclass(slots=True)
class Panel:
    shot_id: str
    revision: int = 0
    status: PanelStatus = PanelStatus.PENDING
    image: MediaRef | None = None
    response_id: str | None = None
    size: Size | None = None
    masks: dict[str, ObjectMask] = field(default_factory=dict)
    transforms: list[CanvasTransform] = field(default_factory=list)  # one geometry layer per object, on the base
    outdated: bool = False  # the shot changed after this was drawn (a reveal, a merge, a removed character)
    plates: dict[str, CleanPlate] = field(default_factory=dict)  # by plate_key, for the current base revision
    composite: Composite | None = None
    review: PanelReview | None = None  # the continuity supervisor's word on this base revision
    versions: list[PanelVersion] = field(default_factory=list)  # earlier drawings, newest first
    suggested_change: str | None = None  # after a refusal: a plainer change to offer (ADR 0022)

    @property
    def current_revision(self) -> int:
        """The newest revision: a composite of the base render, or the base render itself."""
        return self.composite.revision if self.composite else self.revision

    @property
    def shown_image(self) -> MediaRef | None:
        return self.composite.image if self.composite else self.image

    @property
    def shown_size(self) -> Size | None:
        return self.composite.size if self.composite else self.size

    def record_render(self, revision: int, image: MediaRef, response_id: str, size: Size) -> None:
        """A new model render. Revisions only increase.

        Masks, clean plates and the composite of older revisions are dropped. Layers of characters are kept:
        pre-segmented character masks use stable ids (``character:<id>``), so those layers re-apply once the new
        revision is segmented. Layers of clicked objects cannot be found again and are dropped.
        """
        if revision <= self.revision:
            raise RevisionOrderError(f"panel {self.shot_id}: revision {revision} is not after {self.revision}")
        revision = max(revision, self.current_revision + 1)  # a composite took the number meanwhile: the next one
        self._keep_shown()
        self.transforms = [t for t in self.transforms if t.object_id.startswith("character:")]
        self.plates, self.composite = {}, None
        self.revision, self.image, self.response_id, self.size = revision, image, response_id, size
        self.status = PanelStatus.READY
        self.masks = {}
        self.outdated = False
        self.review = None  # a new render is reviewed afresh
        self.suggested_change = None

    def _keep_shown(self) -> None:
        """Keep what is shown now as a version, before something replaces it."""
        image, size = self.shown_image, self.shown_size
        if self.status is not PanelStatus.READY or image is None or size is None or self.response_id is None:
            return
        review = self.review if self.review and self.review.revision == self.revision else None
        kept = PanelVersion(self.current_revision, image, size, self.response_id, review)
        self.versions = [kept, *(v for v in self.versions if v.image != image)][:KEEP_VERSIONS]

    def use_version(self, revision: int) -> None:
        """Show an earlier drawing again, as the next revision; what was shown becomes a version itself.

        The drawing is restored as it was shown, moves included, so it becomes a plain render with no layers.
        """
        version = next((v for v in self.versions if v.revision == revision), None)
        if version is None:
            raise UnknownObjectError(f"panel {self.shot_id}: no earlier version {revision}")
        new = self.current_revision + 1
        self._keep_shown()
        self.versions = [v for v in self.versions if v.revision != revision]
        self.revision, self.image, self.response_id, self.size = new, version.image, version.response_id, version.size
        self.status, self.composite, self.plates, self.masks, self.transforms = PanelStatus.READY, None, {}, {}, []
        self.outdated = False
        self.review = replace(version.review, revision=new) if version.review else None
        self.suggested_change = None

    def mark_failed(self, suggested_change: str | None = None) -> None:
        """The drawing failed. A panel that was drawn before keeps showing that drawing."""
        self.suggested_change = suggested_change
        if self.status is PanelStatus.READY and self.image is not None:
            return
        self.status = PanelStatus.FAILED

    def require_ready(self) -> tuple[MediaRef, str]:
        if self.status is not PanelStatus.READY or self.image is None or self.response_id is None:
            raise PanelNotReadyError(f"panel {self.shot_id} has no ready render")
        return self.image, self.response_id

    def has_render(self, revision: int) -> bool:
        return self.status is PanelStatus.READY and self.revision >= revision

    def cache_mask(self, revision: int, mask: ObjectMask) -> bool:
        """Cache a mask for `revision`. Returns False (and drops it) if the panel moved on."""
        if revision != self.revision:
            return False
        self.masks[mask.id] = mask
        return True

    def mask_at(self, p: Point) -> ObjectMask | None:
        hits = [m for m in self.masks.values() if m.bitmap.contains(p)]
        # Smallest object wins, so a prop in front of a character is selectable.
        return min(hits, key=lambda m: len(m.bitmap.data), default=None)

    def transform(self, t: CanvasTransform) -> None:
        """Set an object's geometry layer, replacing its previous one. Moving it back home removes the layer."""
        if t.object_id not in self.masks:
            raise UnknownObjectError(f"panel {self.shot_id}: no object {t.object_id!r} on revision {self.revision}")
        if self.masks[t.object_id].cutout is None:
            raise UnknownObjectError(f"panel {self.shot_id}: object {t.object_id!r} has no cut-out to move")
        self.transforms = [x for x in self.transforms if x.object_id != t.object_id]
        if not t.is_identity:
            self.transforms.append(t)

    def layers(self) -> list[tuple[ObjectMask, CanvasTransform]]:
        """The geometry layers whose objects are segmented on the current base revision."""
        return [(self.masks[t.object_id], t) for t in self.transforms if t.object_id in self.masks]

    def cache_plate(self, base_revision: int, plate: CleanPlate) -> bool:
        if base_revision != self.revision:
            return False  # a new render replaced the base this plate was made from
        self.plates[plate.key] = plate
        return True

    def record_composite(self, base_revision: int, image: MediaRef, size: Size) -> Composite | None:
        """The layers applied to base `base_revision`, as the next revision. Ignored if the base moved on."""
        if base_revision != self.revision or self.status is not PanelStatus.READY:
            return None
        self.composite = Composite(self.current_revision + 1, image, size)
        return self.composite

    def record_review(self, review: PanelReview) -> bool:
        """Keep a review of the base revision it checked. Returns False (and drops it) if the panel moved on."""
        if review.revision != self.revision or self.status is not PanelStatus.READY:
            return False
        self.review = review
        return True

    def clear_composite(self) -> None:
        """Every layer was moved back: the base render is shown again."""
        self.composite = None
