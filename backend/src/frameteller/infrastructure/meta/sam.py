"""MetaSamAdapter: object selection with SAM 3.1 (ADR 0005, 0006). Output is parsed only by meta_sam_parser."""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import Any

import numpy as np
from meta_sam_parser import (
    FramePrompt,
    PromptObject,
    PromptPoint,
    SegmentationMaskRecord,
    build_object_prompt,
    decode_mask_to_raster,
    image_segmentation_format,
    parse_responses_stream,
)
from openai import AsyncOpenAI
from PIL import Image

from frameteller.application.ports import MediaStoragePort, Segment
from frameteller.domain import Box, MaskBitmap, MediaRef, Point, Size
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.meta.images import as_png, data_url, inspect_image
from frameteller.infrastructure.pricing import SAM_IMAGE_USD
from frameteller.infrastructure.resilience import ModelCaller, RetryPolicy, Usage


class MetaSamAdapter:
    """SegmentationPort. Masks come back cropped to their box; they are placed at that box and stored as cut-outs."""

    def __init__(self, client: AsyncOpenAI, caller: ModelCaller, storage: MediaStoragePort, settings: Settings) -> None:
        self._client, self._caller, self._storage, self._settings = client, caller, storage, settings
        self._policy = RetryPolicy(attempts=settings.retry_attempts, timeout_s=settings.sam_timeout_s)

    async def segment_concept(self, image: MediaRef, concept: str, store_prefix: str) -> list[Segment]:
        data = await self._storage.get(image)
        size, _ = inspect_image(data)
        records = await self._segment(data, concept.strip(), "segment_concept")
        return await self._segments(records, data, size, concept, store_prefix)

    async def segment_point(self, image: MediaRef, point: Point, store_prefix: str) -> Segment | None:
        data = await self._storage.get(image)
        size, _ = inspect_image(data)
        x, y = min(max(point.x, 0), size.width - 1), min(max(point.y, 0), size.height - 1)
        prompt = build_object_prompt(
            size=(size.width, size.height),
            objects=[PromptObject(id=1, prompts=[FramePrompt(frame=0, points=[PromptPoint(x, y)])])],
        )
        records = await self._segment(data, prompt, "segment_point")
        segments = await self._segments(records, data, size, "", store_prefix)
        return segments[0] if segments else None

    async def _segment(self, image: bytes, text: str, operation: str) -> list[SegmentationMaskRecord]:
        model = self._settings.sam_model
        image_url = data_url(as_png(image), "image/png")

        # A noun phrase OR object prompts in the text part, never both.
        message: Any = {
            "role": "user",
            "content": [{"type": "input_text", "text": text}, {"type": "input_image", "image_url": image_url}],
        }

        async def call() -> tuple[list[SegmentationMaskRecord], Usage]:
            stream = await self._client.responses.create(model=model, input=[message], stream=True)
            result = await parse_responses_stream(stream, image_segmentation_format()).final_result()
            masks = [r for r in result.records if isinstance(r, SegmentationMaskRecord)]
            return masks, Usage(SAM_IMAGE_USD)

        return await self._caller.call(model, operation, call, self._policy)

    async def _segments(
        self, records: Sequence[SegmentationMaskRecord], image: bytes, size: Size, label: str, store_prefix: str
    ) -> list[Segment]:
        segments = []
        for n, rec in enumerate(records):
            bitmap = place_mask(rec, size)
            if bitmap is None:
                continue
            cutout = await self._storage.put(f"{store_prefix}/cutout-{n}.png", cut_out(image, bitmap), "image/png")
            segments.append(Segment(bitmap.box, bitmap, label, cutout))
        return segments


def place_mask(rec: SegmentationMaskRecord, size: Size) -> MaskBitmap | None:
    """Put the box-sized raster at its box position, clipped to the image."""
    m = rec.mask
    raster = np.frombuffer(decode_mask_to_raster(m), dtype=np.uint8).reshape(m.height, m.width)
    left, top = int(rec.bounds.left), int(rec.bounds.top)
    right, bottom = min(left + m.width, size.width), min(top + m.height, size.height)
    if right <= left or bottom <= top:
        return None
    clipped = np.ascontiguousarray(raster[: bottom - top, : right - left])
    return MaskBitmap(Box(left, top, right, bottom), clipped.tobytes())


def cut_out(image: bytes, bitmap: MaskBitmap) -> bytes:
    """RGBA crop of the object: panel pixels with the mask as alpha, for canvas moves (ADR 0005)."""
    b = bitmap.box
    with Image.open(io.BytesIO(image)) as im:
        crop = im.convert("RGBA").crop((b.left, b.top, b.right, b.bottom))
    alpha = np.frombuffer(bitmap.data, dtype=np.uint8).reshape(b.bottom - b.top, b.right - b.left) * 255
    crop.putalpha(Image.fromarray(alpha.astype(np.uint8), "L"))
    buf = io.BytesIO()
    crop.save(buf, "PNG")
    return buf.getvalue()
