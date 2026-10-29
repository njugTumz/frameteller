import pytest

from frameteller.application import costs
from frameteller.application.jobs import PRE_SEGMENT_PANEL, SUPERVISE_PANEL
from frameteller.application.use_cases import EditPanelAppearance, GenerateCharacterReference, GeneratePanel
from frameteller.domain import (
    CastNotApprovedError,
    CastStatus,
    MediaRef,
    PanelNotReadyError,
    PanelStatus,
    PanelStyle,
    Size,
)
from tests.application.conftest import World


def generate(w: World) -> GeneratePanel:
    return GeneratePanel(w.repo, w.images, w.budget, w.jobs)


def edit(w: World) -> EditPanelAppearance:
    return EditPanelAppearance(w.repo, w.images, w.budget, w.jobs)


async def test_generate_reference_stores_it_and_returns_cast_to_draft(world: World) -> None:
    cat = await GenerateCharacterReference(world.repo, world.images, world.budget).execute("p1", "cat")
    ref = cat.reference
    assert ref is not None
    p = world.project()
    assert p.bible.get("cat").reference == ref
    assert p.bible.status is CastStatus.DRAFT
    assert world.images.generated[0].quality == "high"
    assert world.images.generated[0].aspect == "square"
    assert ref.key in world.storage.files
    assert world.budget.charges == [("p1", costs.IMAGE, "reference cat")]


async def test_cast_not_approved_blocks_panel_generation(draft_world: World) -> None:
    with pytest.raises(CastNotApprovedError):
        await generate(draft_world).execute("p1", "s1", revision=1)
    assert draft_world.images.calls == 0
    assert draft_world.budget.charges == []


async def test_generate_panel_uses_the_shot_cast_references(world: World) -> None:
    panel = await generate(world).execute("p1", "s2", revision=1)
    request = world.images.generated[0]
    assert request.references == (MediaRef("refs/mira.webp"), MediaRef("refs/cat.webp"))
    assert request.aspect == "panel"
    assert panel.status is PanelStatus.READY
    assert panel.image is not None
    assert panel.image.key in world.storage.files
    assert panel.size == Size(1920, 1280)
    assert world.project().panel("s2").response_id == "resp_1"


async def test_idempotent_generate_panel_does_not_call_the_image_port_twice(world: World) -> None:
    use_case = generate(world)
    first = await use_case.execute("p1", "s1", revision=1)
    second = await use_case.execute("p1", "s1", revision=1)
    assert world.images.calls == 1
    assert len(world.budget.charges) == 1
    assert second.image == first.image


async def test_generate_panel_queues_pre_segmentation_once(world: World) -> None:
    await generate(world).execute("p1", "s1", revision=1)
    await generate(world).execute("p1", "s1", revision=1)
    assert [(j.kind, j.idempotency_key) for j in world.jobs.jobs] == [
        (PRE_SEGMENT_PANEL, "pre_segment_panel:p1:s1:r1"),
        (SUPERVISE_PANEL, "supervise_panel:p1:s1:r1"),
    ]


async def test_failed_render_marks_panel_failed_and_reraises(world: World) -> None:
    world.images.fail_next = True
    with pytest.raises(RuntimeError, match="unavailable"):
        await generate(world).execute("p1", "s1", revision=1)
    assert world.project().panel("s1").status is PanelStatus.FAILED
    assert world.jobs.jobs == []


async def test_edit_chains_the_previous_response_and_names_every_part(world: World) -> None:
    await generate(world).execute("p1", "s1", revision=1)
    panel = await edit(world).execute("p1", "s1", "raincoat", ["hood", "sleeves"], "make it red")

    previous_id, prompt = world.images.edits[0]
    assert previous_id == "resp_1"
    assert "the hood" in prompt
    assert "the sleeves" in prompt
    assert panel.revision == 2
    assert world.project().panel("s1").response_id == "resp_2"
    assert world.jobs.jobs[-1].idempotency_key == "pre_segment_panel:p1:s1:r2"


async def test_edit_needs_a_ready_panel(world: World) -> None:
    with pytest.raises(PanelNotReadyError):
        await edit(world).execute("p1", "s1", "raincoat", ["hood"], "make it red")
    assert world.images.calls == 0


async def test_edit_is_blocked_while_cast_is_draft(draft_world: World) -> None:
    with pytest.raises(CastNotApprovedError):
        await edit(draft_world).execute("p1", "s1", "raincoat", ["hood"], "make it red")


async def test_panels_and_reference_sheets_follow_the_project_style(world: World) -> None:
    await world.repo.update("p1", lambda p: setattr(p, "style", PanelStyle.PAPER_CUTOUT))
    await GenerateCharacterReference(world.repo, world.images, world.budget).execute("p1", "cat")
    await world.repo.update("p1", lambda p: p.bible.approve())
    await generate(world).execute("p1", "s2", revision=1)
    assert all("paper cutout" in r.prompt for r in world.images.generated)
