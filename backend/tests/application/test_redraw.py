"""Redraw (ADR 0022): a new take with what should change, a plain message after a refusal, and Keep previous."""

import pytest

from frameteller.application.errors import ModelContentFilteredError
from frameteller.application.jobs import GENERATE_PANEL, PRE_SEGMENT_PANEL, SUPERVISE_PANEL
from frameteller.application.prompts import TAKES, Redraw, panel_prompt
from frameteller.application.use_cases import GeneratePanel, RequestPanelRender, UsePanelVersion
from frameteller.application.use_cases.generate_panel import PanelRefusedError
from frameteller.domain import InvalidValueError, MediaRef, PanelStatus
from tests.application.conftest import World
from tests.builders import CAT, MIRA, shot

REFUSED = ModelContentFilteredError("muse-image-1.0", "HTTP 400 content filter")


def generate(w: World) -> GeneratePanel:
    return GeneratePanel(w.repo, w.images, w.budget, w.jobs)


# ---- the prompt ----


def test_a_plain_redraw_moves_the_camera_and_keeps_the_shot() -> None:
    s = shot(1, "mira")
    first = panel_prompt(s, [MIRA, CAT])
    takes = {panel_prompt(s, [MIRA, CAT], redraw=Redraw(), revision=r) for r in range(2, 2 + len(TAKES))}
    assert len(takes) == len(TAKES)  # every take differs from the last
    take = panel_prompt(s, [MIRA, CAT], redraw=Redraw(), revision=2)
    assert first not in take
    assert "new take on the shot: a different composition with " + TAKES[2 % len(TAKES)] in take
    assert "Keep the same characters, clothes, setting and action." in take
    assert f"Action: {s.action}" in take  # the shot keeps its meaning


def test_surprise_me_is_bolder_and_the_change_is_said_as_the_directors() -> None:
    surprise = panel_prompt(shot(1, "mira"), [MIRA], redraw=Redraw(surprise=True), revision=3)
    assert "bold new take" in surprise
    assert "dramatic lighting" in surprise
    changed = panel_prompt(shot(1, "mira"), [MIRA], redraw=Redraw("make it night."), revision=3)
    assert "The director asks for this change: make it night." in changed


def test_the_change_is_cleaned_like_every_prompt_and_said_plainer_on_the_retry() -> None:
    redraw = Redraw("show my 6-year-old daughter closer")
    assert "6-year-old" not in panel_prompt(shot(1, "mira"), [MIRA], redraw=redraw, revision=2)
    safer = panel_prompt(shot(1, "mira"), [MIRA], redraw=redraw, revision=2, safer=True)
    assert "daughter" not in safer
    assert "child" not in safer


# ---- the request ----


async def test_a_redraw_queues_the_next_revision_with_its_change(world: World) -> None:
    await generate(world).execute("p1", "s1", 1)
    requests = RequestPanelRender(world.repo, world.jobs)
    ticket = await requests.execute("p1", "s1", "low", redraw=Redraw(" make it night "))
    assert (ticket.kind, ticket.revision) == (GENERATE_PANEL, 2)
    payload = world.jobs.jobs[-1].payload
    assert (payload["redraw"], payload["change"]) == ("new", "make it night")

    again = await requests.execute("p1", "s1", "low", redraw=Redraw(surprise=True))
    assert not again.enqueued  # same revision: deduplicated, never charged twice


async def test_draw_final_is_not_a_new_take(world: World) -> None:
    await generate(world).execute("p1", "s1", 1)
    await RequestPanelRender(world.repo, world.jobs).execute("p1", "s1", "high")
    assert "redraw" not in world.jobs.jobs[-1].payload


async def test_what_should_change_has_a_limit(world: World) -> None:
    with pytest.raises(InvalidValueError):
        await RequestPanelRender(world.repo, world.jobs).execute("p1", "s1", "low", redraw=Redraw("x" * 301))


async def test_a_redraw_is_drawn_with_its_take_and_checked_by_the_supervisor(world: World) -> None:
    await generate(world).execute("p1", "s1", 1)
    await generate(world).execute("p1", "s1", 2, redraw=Redraw("make it night"))
    first, redrawn = world.images.generated[-2:]
    assert "make it night" in redrawn.prompt
    assert redrawn.references == first.references  # the approved sheets, as before
    assert "make it night" in (world.images.generated[-1].fallback_prompt or "")
    assert (SUPERVISE_PANEL, "supervise_panel:p1:s1:r2") in [(j.kind, j.idempotency_key) for j in world.jobs.jobs]
    assert len(world.budget.charges) == 2  # a redraw costs a render, as before
    assert [v.revision for v in world.project().panel("s1").versions] == [1]


# ---- refusals ----


async def test_a_refused_redraw_keeps_the_drawing_and_offers_a_plainer_change(world: World) -> None:
    await generate(world).execute("p1", "s1", 1)
    world.images.refuse = [REFUSED]
    with pytest.raises(PanelRefusedError) as raised:
        await generate(world).execute("p1", "s1", 2, redraw=Redraw("something odd"))
    assert "say plainly what happens" in raised.value.user_message
    panel = world.project().panel("s1")
    assert panel.status is PanelStatus.READY
    assert panel.image == MediaRef("projects/p1/panels/s1/r1/image")
    assert panel.suggested_change is not None
    assert panel.suggested_change.startswith("keep it calm and friendly: ")


async def test_a_refused_first_drawing_fails_with_the_suggestion(world: World) -> None:
    world.images.refuse = [REFUSED]
    with pytest.raises(PanelRefusedError):
        await generate(world).execute("p1", "s1", 1)
    panel = world.project().panel("s1")
    assert panel.status is PanelStatus.FAILED
    assert panel.suggested_change


# ---- Keep previous ----


async def test_keep_previous_shows_the_earlier_drawing_again_for_free(world: World) -> None:
    await generate(world).execute("p1", "s1", 1)
    await generate(world).execute("p1", "s1", 2, redraw=Redraw())
    charges, calls = len(world.budget.charges), world.images.calls

    shown = await UsePanelVersion(world.repo, world.jobs).execute("p1", "s1", 1)

    panel = world.project().panel("s1")
    assert shown == 3
    assert panel.image == MediaRef("projects/p1/panels/s1/r1/image")
    assert [v.revision for v in panel.versions] == [2]  # Use new is one click away again
    assert (len(world.budget.charges), world.images.calls) == (charges, calls)
    assert world.jobs.jobs[-1].kind == PRE_SEGMENT_PANEL
    assert world.jobs.jobs[-1].payload["revision"] == "3"
