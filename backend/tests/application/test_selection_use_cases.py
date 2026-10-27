import pytest

from frameteller.application import costs
from frameteller.application.errors import NothingToSegmentError
from frameteller.application.ports import Segment
from frameteller.application.use_cases import (
    ExportAnimatic,
    GeneratePanel,
    MovePanelObject,
    PreSegmentPanel,
    SegmentObjectAtPoint,
    character_mask_id,
)
from frameteller.domain import MediaRef, PanelNotReadyError, Point, Size, UnknownObjectError
from tests.application.conftest import World
from tests.builders import bitmap
from tests.fakes import FakeVideoRenderer

MIRA_SEGMENT = Segment(bitmap(100, 100, 300, 400).box, bitmap(100, 100, 300, 400), "Mira")
CAT_SEGMENT = Segment(bitmap(320, 300, 380, 360).box, bitmap(320, 300, 380, 360), "Grey Cat")


async def render(w: World, shot_id: str = "s2") -> None:
    await GeneratePanel(w.repo, w.images, w.budget, w.jobs).execute("p1", shot_id, revision=1)


def pre_segment(w: World) -> PreSegmentPanel:
    return PreSegmentPanel(w.repo, w.sam, w.budget)


def click(w: World) -> SegmentObjectAtPoint:
    return SegmentObjectAtPoint(w.repo, w.sam, w.budget, w.ids)


async def test_pre_segment_caches_each_character_with_a_stable_id(world: World) -> None:
    world.sam.by_concept = {"Mira": MIRA_SEGMENT, "Grey Cat": CAT_SEGMENT}
    await render(world)
    masks = await pre_segment(world).execute("p1", "s2", revision=1)

    assert [m.id for m in masks] == [character_mask_id("mira"), character_mask_id("cat")]
    assert set(world.project().panel("s2").masks) == {"character:mira", "character:cat"}
    assert world.sam.concept_calls == ["Mira", "Grey Cat"]
    assert sum(c for _, c, w in world.budget.charges if w.startswith("pre-segment")) == pytest.approx(
        2 * costs.SAM_IMAGE
    )


async def test_pre_segment_skips_stale_revisions_and_cached_masks(world: World) -> None:
    world.sam.by_concept = {"Mira": MIRA_SEGMENT, "Grey Cat": CAT_SEGMENT}
    await render(world)
    assert await pre_segment(world).execute("p1", "s2", revision=0) == []
    await pre_segment(world).execute("p1", "s2", revision=1)
    assert await pre_segment(world).execute("p1", "s2", revision=1) == []
    assert world.sam.concept_calls == ["Mira", "Grey Cat"]


async def test_pre_segment_tolerates_a_character_sam_cannot_find(world: World) -> None:
    world.sam.by_concept = {"Mira": MIRA_SEGMENT}
    await render(world)
    masks = await pre_segment(world).execute("p1", "s2", revision=1)
    assert [m.id for m in masks] == ["character:mira"]


async def test_cached_mask_hit_skips_the_segmentation_port(world: World) -> None:
    world.sam.by_concept = {"Mira": MIRA_SEGMENT, "Grey Cat": CAT_SEGMENT}
    await render(world)
    await pre_segment(world).execute("p1", "s2", revision=1)
    charges_before = len(world.budget.charges)

    mask = await click(world).execute("p1", "s2", Point(150, 200))

    assert mask.id == "character:mira"
    assert world.sam.point_calls == []
    assert len(world.budget.charges) == charges_before


async def test_click_miss_calls_sam_once_then_hits_the_cache(world: World) -> None:
    world.sam.at_point = Segment(bitmap(500, 50, 560, 90).box, bitmap(500, 50, 560, 90), "lamp")
    await render(world)
    first = await click(world).execute("p1", "s2", Point(520, 60))
    second = await click(world).execute("p1", "s2", Point(530, 70))

    assert first.id == second.id == "object:obj1"
    assert first.label == "lamp"
    assert world.sam.point_calls == [Point(520, 60)]


async def test_preview_click_is_converted_to_media_pixels_before_the_cache_check(world: World) -> None:
    world.sam.by_concept = {"Mira": MIRA_SEGMENT}
    await render(world)  # 1920x1280 panel
    await pre_segment(world).execute("p1", "s2", revision=1)
    # (75, 100) on a 960x640 preview is (150, 200) in the panel: inside Mira
    mask = await click(world).execute("p1", "s2", Point(75, 100), shown=Size(960, 640))
    assert mask.id == "character:mira"
    assert world.sam.point_calls == []


async def test_click_on_nothing_raises(world: World) -> None:
    await render(world)
    with pytest.raises(NothingToSegmentError):
        await click(world).execute("p1", "s2", Point(5, 5))


async def test_click_needs_a_ready_panel(world: World) -> None:
    with pytest.raises(PanelNotReadyError):
        await click(world).execute("p1", "s2", Point(5, 5))


async def test_move_object_records_a_canvas_transform_without_model_calls(world: World) -> None:
    world.sam.by_concept = {"Mira": MIRA_SEGMENT}
    await render(world)
    await pre_segment(world).execute("p1", "s2", revision=1)
    calls = world.images.calls

    t = await MovePanelObject(world.repo).execute("p1", "s2", "character:mira", dx=40, scale=1.2)

    assert world.project().panel("s2").transforms == [t]
    assert world.images.calls == calls


async def test_move_unknown_object_fails(world: World) -> None:
    await render(world)
    with pytest.raises(UnknownObjectError):
        await MovePanelObject(world.repo).execute("p1", "s2", "character:ghost", dx=1)


async def test_export_renders_every_panel_with_narration(world: World) -> None:
    for shot_id in ("s1", "s2", "s3"):
        await render(world, shot_id)
    world.storage.files["audio/take.wav"] = (b"wav", "audio/wav")
    renderer = FakeVideoRenderer()

    ref = await ExportAnimatic(world.repo, world.storage, renderer).execute("p1", MediaRef("audio/take.wav"))

    animatic, frames, narration = renderer.rendered[0]
    assert [c.shot_id for c in animatic.clips] == ["s1", "s2", "s3"]
    assert set(frames) == {"s1", "s2", "s3"}
    assert narration == b"wav"
    assert world.storage.files[ref.key] == (b"mp4", "video/mp4")


async def test_export_without_narration(world: World) -> None:
    for shot_id in ("s1", "s2", "s3"):
        await render(world, shot_id)
    renderer = FakeVideoRenderer()
    await ExportAnimatic(world.repo, world.storage, renderer).execute("p1")
    assert renderer.rendered[0][2] is None


async def test_export_needs_every_panel(world: World) -> None:
    await render(world, "s1")
    with pytest.raises(PanelNotReadyError):
        await ExportAnimatic(world.repo, world.storage, FakeVideoRenderer()).execute("p1")
