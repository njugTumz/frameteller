import io

from PIL import Image

from frameteller.application.ports import CutoutLayer
from frameteller.domain import Size
from frameteller.infrastructure.imaging.compositor import PillowCompositor


def pixel(image: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    r, g, b = image.convert("RGB").getpixel((x, y))  # type: ignore[misc]
    return r, g, b


def png(width: int, height: int, colour: tuple[int, int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (width, height), colour).save(out, "PNG")
    return out.getvalue()


async def test_cut_outs_are_pasted_at_their_place_and_scale_with_transparency_kept() -> None:
    plate = png(200, 100, (255, 255, 255, 255))
    red = Image.new("RGBA", (20, 10), (0, 0, 0, 0))
    red.paste((255, 0, 0, 255), (0, 0, 10, 10))  # the right half is transparent
    buffer = io.BytesIO()
    red.save(buffer, "PNG")

    data = await PillowCompositor().compose(plate, [CutoutLayer(buffer.getvalue(), 50, 20, 2.0)], Size(200, 100))

    with Image.open(io.BytesIO(data)) as out:
        assert out.format == "WEBP"
        assert out.size == (200, 100)
        r, g, _ = pixel(out, 60, 30)  # inside the scaled red square (50..70, 20..40)
        assert r > 200
        assert g < 60
        assert pixel(out, 80, 30)[1] > 200  # the transparent half leaves the plate showing
        assert pixel(out, 10, 10)[1] > 200


async def test_layers_off_the_edge_are_clipped_and_the_plate_is_resized_to_the_panel() -> None:
    plate = png(100, 50, (255, 255, 255, 255))
    cut = png(40, 40, (0, 0, 255, 255))

    data = await PillowCompositor().compose(plate, [CutoutLayer(cut, -20, -20, 1.0)], Size(200, 100))

    with Image.open(io.BytesIO(data)) as out:
        assert out.size == (200, 100)
        assert pixel(out, 5, 5)[2] > 200
