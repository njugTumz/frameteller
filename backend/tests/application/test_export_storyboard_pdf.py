from collections.abc import Sequence

import pytest

from frameteller.application.ports import SheetRow
from frameteller.application.use_cases import ExportStoryboardPdf, GeneratePanel
from frameteller.domain import PanelNotReadyError
from tests.application.conftest import World, make_world
from tests.builders import project


class RecordingSheet:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[SheetRow]]] = []

    async def render(self, title: str, rows: Sequence[SheetRow]) -> bytes:
        self.calls.append((title, list(rows)))
        return b"%PDF-1.4"


async def test_every_shot_in_order_drawn_or_not(world: World) -> None:
    await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", "s2", revision=1)
    p = world.project()
    p.reorder_shots(["s2", "s1", "s3"])
    await world.repo.save(p)
    sheet = RecordingSheet()

    pdf = await ExportStoryboardPdf(world.repo, world.storage, sheet).execute("p1")

    assert pdf == b"%PDF-1.4"
    [(title, rows)] = sheet.calls
    assert title == "The Lantern Cat"
    assert [(r.number, r.image is not None) for r in rows] == [(1, True), (2, False), (3, False)]
    assert rows[0].framing == "medium"
    assert (rows[0].action, rows[0].duration_ms) == ("action 2", 4000)


async def test_a_project_without_shots_has_nothing_to_print() -> None:
    w = make_world(project(shots=0))
    with pytest.raises(PanelNotReadyError):
        await ExportStoryboardPdf(w.repo, w.storage, RecordingSheet()).execute("p1")
