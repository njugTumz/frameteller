import io
from pathlib import Path

from PIL import Image

from frameteller.infrastructure.imaging.share_preview import contact_sheet
from frameteller.infrastructure.local import FileShareIndex


async def test_file_share_index(tmp_path: Path) -> None:
    index = FileShareIndex(tmp_path)
    await index.put("abc123", "p1")
    assert await index.find("abc123") == "p1"
    assert await index.find("missing") is None
    assert await index.find("../escape") is None
    await index.delete("abc123")
    await index.delete("abc123")
    assert await index.find("abc123") is None


def test_contact_sheet_is_a_1200x630_png_with_or_without_panels() -> None:
    panel = io.BytesIO()
    Image.new("RGB", (1920, 1280), (200, 180, 150)).save(panel, "WEBP")
    for panels in ([panel.getvalue()] * 7, [], [b"not an image"]):
        with Image.open(io.BytesIO(contact_sheet("The Lighthouse Keeper", panels))) as image:
            assert (image.format, image.size) == ("PNG", (1200, 630))
