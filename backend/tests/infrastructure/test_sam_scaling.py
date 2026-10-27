import io

from PIL import Image

from frameteller.domain import Box, MaskBitmap, Size
from frameteller.infrastructure.meta.sam import scale_mask, shrink
from tests.fixtures import image


def test_shrink_keeps_the_aspect_ratio_and_leaves_small_images_alone() -> None:
    png, small = shrink(image("panel_small.webp"), Size(384, 256), 256)
    assert small == Size(256, 170)
    with Image.open(io.BytesIO(png)) as im:
        assert (im.format, im.size) == ("PNG", (256, 170))
    assert shrink(image("panel_small.webp"), Size(384, 256), 768)[1] == Size(384, 256)
    assert shrink(image("panel_small.webp"), Size(384, 256), None)[1] == Size(384, 256)


def test_scale_mask_maps_box_and_raster_to_full_size() -> None:
    box = Box(10, 20, 30, 40)  # 20x20 square on a 100x50 copy
    bitmap = MaskBitmap(box, bytes([1]) * 400)

    up = scale_mask(bitmap, Size(100, 50), Size(400, 200))

    assert up is not None
    assert abs(up.box.left - 40) <= 2
    assert abs(up.box.top - 80) <= 2
    assert abs(up.box.right - 120) <= 2
    assert abs(up.box.bottom - 160) <= 2
    filled = sum(up.data) / len(up.data)
    assert filled > 0.95  # a solid square stays solid
