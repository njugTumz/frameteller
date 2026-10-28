"""Saved geometry on a clean plate (ADR 0010)."""

import pytest

from frameteller.application import costs
from frameteller.application.ports import CutoutLayer, Segment
from frameteller.application.use_cases import ComposePanel, GeneratePanel, MovePanelObject, PreSegmentPanel
from frameteller.domain import MediaRef
from tests.application.conftest import World
from tests.builders import bitmap
from tests.fakes import FakeCompositor

MIRA_BITMAP, CAT_BITMAP = bitmap(100, 100, 300, 400), bitmap(320, 300, 380, 360)
MIRA = Segment(MIRA_BITMAP.box, MIRA_BITMAP, "Mira", MediaRef("projects/p1/cut-mira.png"))
CAT = Segment(CAT_BITMAP.box, CAT_BITMAP, "Grey Cat", MediaRef("projects/p1/cut-cat.png"))
MIRA_ID, CAT_ID = "character:mira", "character:cat"


@pytest.fixture
async def ready(world: World) -> World:
    """Shot s2 drawn and pre-segmented, with both characters' cut-outs stored."""
    world.sam.by_concept = {"8-year-old girl": MIRA, "small grey kitten with glowing amber eyes": CAT}
    world.storage.files["projects/p1/cut-mira.png"] = (b"mira-cut", "image/png")
    world.storage.files["projects/p1/cut-cat.png"] = (b"cat-cut", "image/png")
    await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", "s2", revision=1)
    await PreSegmentPanel(world.repo, world.sam, world.budget, world.jobs).execute("p1", "s2", revision=1)
    return world


def compose(w: World, compositor: FakeCompositor) -> ComposePanel:
    return ComposePanel(w.repo, w.images, w.storage, compositor, w.budget)


async def move(w: World, object_id: str, **geometry: object) -> None:
    await MovePanelObject(w.repo, w.jobs).execute("p1", "s2", object_id, **geometry)  # type: ignore[arg-type]


async def test_first_move_removes_the_object_once_then_pastes_its_cut_out(ready: World) -> None:
    compositor = FakeCompositor()
    await move(ready, MIRA_ID, dx=40, dy=-10, scale=1.5)
    spent = ready.budget.total

    composite = await compose(ready, compositor).execute("p1", "s2", 1)

    assert composite is not None
    [(response_id, prompt)] = ready.images.edits
    assert response_id == "resp_1"  # chained from the base render
    assert prompt.startswith("Remove the 8-year-old girl")  # a visual phrase, not the name
    assert "Keep everything else identical" in prompt
    assert ready.budget.total == pytest.approx(spent + costs.IMAGE)
    [(background, layers, size)] = compositor.calls
    assert background == b"image-2"  # the clean plate
    assert layers == [CutoutLayer(b"mira-cut", 140, 90, 1.5)]
    panel = ready.project().panel("s2")
    assert panel.revision == 1  # masks and edits still belong to the render
    assert (panel.current_revision, panel.shown_image) == (2, composite.image)
    assert ready.storage.files[composite.image.key][0] == b"composite-image-2"
    assert size == panel.size


async def test_moving_the_same_object_again_reuses_its_clean_plate(ready: World) -> None:
    compositor = FakeCompositor()
    await move(ready, MIRA_ID, dx=40)
    await compose(ready, compositor).execute("p1", "s2", 1)
    await move(ready, MIRA_ID, dx=80)
    await compose(ready, compositor).execute("p1", "s2", 1)

    assert len(ready.images.edits) == 1
    assert compositor.calls[-1][1] == [CutoutLayer(b"mira-cut", 180, 100, 1.0)]
    assert ready.project().panel("s2").current_revision == 3


async def test_a_second_object_chains_one_more_removal_from_the_first_plate(ready: World) -> None:
    compositor = FakeCompositor()
    await move(ready, MIRA_ID, dx=40)
    await compose(ready, compositor).execute("p1", "s2", 1)
    await move(ready, CAT_ID, deleted=True)
    await compose(ready, compositor).execute("p1", "s2", 1)

    assert [r for r, _ in ready.images.edits] == ["resp_1", "resp_2"]
    assert "Grey Cat" not in ready.images.edits[1][1]
    _, layers, _ = compositor.calls[-1]
    assert layers == [CutoutLayer(b"mira-cut", 140, 100, 1.0)]  # the deleted cat is just not pasted back
    assert set(ready.project().panel("s2").plates) == {MIRA_ID, f"{CAT_ID}+{MIRA_ID}"}


async def test_moving_back_home_shows_the_render_again(ready: World) -> None:
    compositor = FakeCompositor()
    await move(ready, MIRA_ID, dx=40)
    await compose(ready, compositor).execute("p1", "s2", 1)
    await move(ready, MIRA_ID, dx=0)

    assert await compose(ready, compositor).execute("p1", "s2", 1) is None
    panel = ready.project().panel("s2")
    assert panel.composite is None
    assert panel.shown_image == panel.image


async def test_moving_back_to_an_earlier_arrangement_composes_again(ready: World) -> None:
    await move(ready, MIRA_ID, dx=40)
    first = ready.jobs.jobs[-1].idempotency_key
    await compose(ready, FakeCompositor()).execute("p1", "s2", 1)
    await move(ready, MIRA_ID, dx=80)
    await move(ready, MIRA_ID, dx=40)
    assert ready.jobs.jobs[-1].idempotency_key != first


async def test_a_stale_job_for_a_replaced_render_does_nothing(ready: World) -> None:
    await move(ready, MIRA_ID, dx=40)
    await GeneratePanel(ready.repo, ready.images, ready.budget, ready.jobs).execute("p1", "s2", revision=2)
    compositor = FakeCompositor()

    assert await compose(ready, compositor).execute("p1", "s2", 1) is None
    assert compositor.calls == []


async def test_character_layers_come_back_after_a_new_render_is_segmented(ready: World) -> None:
    await move(ready, MIRA_ID, dx=40)
    await compose(ready, FakeCompositor()).execute("p1", "s2", 1)  # shown revision 2
    await GeneratePanel(ready.repo, ready.images, ready.budget, ready.jobs).execute("p1", "s2", revision=3)
    panel = ready.project().panel("s2")
    assert (panel.revision, panel.composite, panel.plates) == (3, None, {})
    assert [t.object_id for t in panel.transforms] == [MIRA_ID]

    await PreSegmentPanel(ready.repo, ready.sam, ready.budget, ready.jobs).execute("p1", "s2", revision=3)

    job = ready.jobs.jobs[-1]
    assert (job.kind, job.payload["revision"]) == ("compose_panel", "3")


async def test_a_new_render_after_a_composite_takes_the_next_number(ready: World) -> None:
    await move(ready, MIRA_ID, dx=40)
    await compose(ready, FakeCompositor()).execute("p1", "s2", 1)  # shown revision 2
    await GeneratePanel(ready.repo, ready.images, ready.budget, ready.jobs).execute("p1", "s2", revision=2)
    panel = ready.project().panel("s2")
    assert panel.revision == 3
    assert ready.jobs.jobs[-1].payload["revision"] == "3"  # pre-segmentation follows the real number
