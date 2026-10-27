"""Image helpers shared by the Muse Image and SAM adapters."""

from __future__ import annotations

import base64
import io

from PIL import Image

from frameteller.domain import Size

_MIME = {"WEBP": "image/webp", "PNG": "image/png", "JPEG": "image/jpeg"}


def inspect_image(data: bytes) -> tuple[Size, str]:
    """Real pixel size and content type of encoded image bytes."""
    with Image.open(io.BytesIO(data)) as im:
        return Size(im.width, im.height), _MIME.get(im.format or "", "application/octet-stream")


def data_url(data: bytes, content_type: str) -> str:
    return f"data:{content_type};base64," + base64.b64encode(data).decode()


def as_png(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "PNG")
        return buf.getvalue()
