"""Panels, their revisions, cached object masks and canvas operations (ADR 0005, 0006)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from frameteller.domain.errors import (
    InvalidValueError,
    PanelNotReadyError,
    RevisionOrderError,
    UnknownObjectError,
)
from frameteller.domain.media import MediaRef


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
    transforms: list[CanvasTransform] = field(default_factory=list)
    outdated: bool = False  # the shot changed after this was drawn (a reveal, a merge, a removed character)

    def record_render(self, revision: int, image: MediaRef, response_id: str, size: Size) -> None:
        """A new model render. Revisions only increase.

        Masks of older revisions are dropped. Canvas transforms are kept: pre-segmented character masks
        use stable ids (``character:<id>``), so transforms re-apply once the new revision is segmented.
        """
        if revision <= self.revision:
            raise RevisionOrderError(f"panel {self.shot_id}: revision {revision} is not after {self.revision}")
        self.revision, self.image, self.response_id, self.size = revision, image, response_id, size
        self.status = PanelStatus.READY
        self.masks = {}
        self.outdated = False

    def mark_failed(self) -> None:
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
        if t.object_id not in self.masks:
            raise UnknownObjectError(f"panel {self.shot_id}: no object {t.object_id!r} on revision {self.revision}")
        self.transforms.append(t)
