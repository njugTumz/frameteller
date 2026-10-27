import pytest

from frameteller.domain import (
    Box,
    CanvasTransform,
    InvalidValueError,
    MaskBitmap,
    MediaRef,
    ObjectMask,
    Panel,
    PanelNotReadyError,
    PanelStatus,
    Point,
    RevisionOrderError,
    Size,
    UnknownObjectError,
)
from tests.builders import bitmap

SIZE = Size(1920, 1280)


def ready_panel(revision: int = 1) -> Panel:
    panel = Panel("s1")
    panel.record_render(revision, MediaRef(f"panels/s1/r{revision}"), f"resp_{revision}", SIZE)
    return panel


def test_render_makes_panel_ready() -> None:
    panel = ready_panel()
    assert panel.status is PanelStatus.READY
    assert panel.require_ready() == (MediaRef("panels/s1/r1"), "resp_1")


def test_revisions_only_increase() -> None:
    panel = ready_panel(2)
    for stale in (1, 2):
        with pytest.raises(RevisionOrderError):
            panel.record_render(stale, MediaRef("x"), "resp_x", SIZE)
    panel.record_render(3, MediaRef("panels/s1/r3"), "resp_3", SIZE)
    assert panel.revision == 3


def test_pending_or_failed_panel_is_not_ready() -> None:
    panel = Panel("s1")
    with pytest.raises(PanelNotReadyError):
        panel.require_ready()
    panel.mark_failed()
    assert panel.status is PanelStatus.FAILED
    with pytest.raises(PanelNotReadyError):
        panel.require_ready()


def test_has_render_for_this_or_an_earlier_revision() -> None:
    panel = ready_panel(2)
    assert panel.has_render(1)
    assert panel.has_render(2)
    assert not panel.has_render(3)


def test_new_render_drops_masks_but_keeps_transforms() -> None:
    panel = ready_panel()
    panel.cache_mask(1, ObjectMask("character:mira", "Mira", bitmap(0, 0, 10, 10)))
    panel.transform(CanvasTransform("character:mira", dx=5))
    panel.record_render(2, MediaRef("panels/s1/r2"), "resp_2", SIZE)
    assert panel.masks == {}
    assert panel.transforms == [CanvasTransform("character:mira", dx=5)]


def test_mask_for_an_old_revision_is_not_cached() -> None:
    panel = ready_panel(2)
    assert not panel.cache_mask(1, ObjectMask("m", "Mira", bitmap(0, 0, 4, 4)))
    assert panel.masks == {}


def test_mask_at_uses_the_bitmap_not_just_the_box() -> None:
    # 2x2 box where only the top-left cell is set
    mask = ObjectMask("m", "cat", MaskBitmap(Box(10, 10, 12, 12), bytes([1, 0, 0, 0])))
    panel = ready_panel()
    panel.cache_mask(1, mask)
    assert panel.mask_at(Point(10, 10)) == mask
    assert panel.mask_at(Point(11, 11)) is None
    assert panel.mask_at(Point(50, 50)) is None


def test_smallest_overlapping_object_wins() -> None:
    panel = ready_panel()
    girl = ObjectMask("character:mira", "Mira", bitmap(0, 0, 100, 100))
    scarf = ObjectMask("object:1", "scarf", bitmap(40, 40, 60, 50))
    panel.cache_mask(1, girl)
    panel.cache_mask(1, scarf)
    assert panel.mask_at(Point(45, 45)) == scarf
    assert panel.mask_at(Point(5, 5)) == girl


def test_transform_needs_a_known_object() -> None:
    with pytest.raises(UnknownObjectError):
        ready_panel().transform(CanvasTransform("character:ghost", dx=1))


def test_value_objects_are_validated() -> None:
    with pytest.raises(InvalidValueError):
        Box(10, 10, 10, 20)
    with pytest.raises(InvalidValueError):
        MaskBitmap(Box(0, 0, 2, 2), bytes([1]))
    with pytest.raises(InvalidValueError):
        CanvasTransform("m", scale=0)
    assert Box(0, 0, 10, 20).centre == Point(5, 10)
    assert ObjectMask("m", "x", bitmap(1, 2, 3, 4)).box == Box(1, 2, 3, 4)


def test_preview_click_converts_to_media_pixels() -> None:
    media, shown = Size(1920, 1280), Size(960, 640)
    assert Point(486, 322).to_media(shown, media) == Point(972, 644)
    assert Point(1000, 700).to_media(shown, media) == Point(1919, 1279)  # clamped
    assert Point(10, 10).to_media(shown, media, offset=Point(20, 20)) == Point(0, 0)  # left of the image
    assert Point(333, 333).to_media(Size(1000, 1000), Size(100, 100)) == Point(33, 33)  # rounds down


def test_size_must_be_positive() -> None:
    with pytest.raises(InvalidValueError):
        Size(0, 10)
