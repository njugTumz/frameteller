import io

from PIL import Image

from frameteller.application.ports import SheetRow
from frameteller.infrastructure.imaging.storyboard_pdf import PillowStoryboardSheet, render_pdf


def webp(colour: tuple[int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (1920, 1280), colour).save(out, "WEBP")
    return out.getvalue()


def row(n: int, image: bytes | None = None, dialogue: str = "") -> SheetRow:
    return SheetRow(n, "wide", f"Ada climbs the lighthouse stairs, shot {n}. " * 4, dialogue, 3200, image)


async def test_six_shots_a_page_with_undrawn_panels_marked() -> None:
    rows = [row(n, webp((200, 180, 150)) if n % 2 else None, "Who's there?" if n == 1 else "") for n in range(1, 8)]
    pdf = await PillowStoryboardSheet().render("The Lighthouse Keeper", rows)
    assert pdf.startswith(b"%PDF")
    assert b"/Count 2" in pdf  # seven shots: two pages


def test_an_empty_title_still_prints() -> None:
    assert render_pdf("", [row(1)]).startswith(b"%PDF")
