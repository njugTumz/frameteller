import io
import json
from collections.abc import Callable
from typing import Any

import httpx2
from openai import AsyncOpenAI
from PIL import Image

from frameteller.domain import MediaRef, Point
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.local import LocalFileMediaStorage
from frameteller.infrastructure.meta.sam import MetaSamAdapter
from frameteller.infrastructure.resilience import ModelCaller
from tests.fakes import InMemorySpendLedger
from tests.fixtures import image, replay

Client = Callable[[httpx2.MockTransport], AsyncOpenAI]
W, H = 384, 256  # tests/fixtures/images/panel_small.webp


def parts(request: httpx2.Request) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = json.loads(request.content)["input"][0]["content"]
    return content


async def panel(storage: LocalFileMediaStorage) -> MediaRef:
    return await storage.put("panels/s2/r1", image("panel_small.webp"), "image/webp")


async def test_concept_finds_the_girl_and_places_her_mask(
    client_for: Client,
    caller: ModelCaller,
    storage: LocalFileMediaStorage,
    settings: Settings,
    ledger: InMemorySpendLedger,
) -> None:
    transport, seen = replay("sam_concept")
    sam = MetaSamAdapter(client_for(transport), caller, storage, settings)

    [segment] = await sam.segment_concept(await panel(storage), "girl in yellow raincoat", "masks/mira")

    b = segment.box
    assert 0 <= b.left < b.right <= W
    assert 0 <= b.top < b.bottom <= H
    assert len(segment.bitmap.data) == (b.right - b.left) * (b.bottom - b.top)
    area = sum(segment.bitmap.data)
    assert 0.05 < area / (W * H) < 0.5  # the spike measured 17.5% at full size
    assert segment.label == "girl in yellow raincoat"

    assert segment.cutout is not None
    with Image.open(io.BytesIO(await storage.get(segment.cutout))) as cut:
        assert cut.mode == "RGBA"
        assert cut.size == (b.right - b.left, b.bottom - b.top)

    text, img = parts(seen[0])
    assert text == {"type": "input_text", "text": "girl in yellow raincoat"}
    assert img["image_url"].startswith("data:image/png;base64,")
    assert json.loads(seen[0].content)["stream"] is True
    assert [u.cost_usd for u in ledger.usage] == [0.0025]


async def test_point_click_selects_one_object(
    client_for: Client, caller: ModelCaller, storage: LocalFileMediaStorage, settings: Settings
) -> None:
    transport, seen = replay("sam_point")
    sam = MetaSamAdapter(client_for(transport), caller, storage, settings)

    segment = await sam.segment_point(await panel(storage), Point(193, 129), "masks/obj")

    assert segment is not None
    assert segment.box.left <= 193 < segment.box.right
    assert segment.box.top <= 129 < segment.box.bottom
    assert "<|point;x=193;y=129;w=384;h=256|>" in parts(seen[0])[0]["text"]


async def test_point_outside_the_panel_is_clamped(
    client_for: Client, caller: ModelCaller, storage: LocalFileMediaStorage, settings: Settings
) -> None:
    transport, seen = replay("sam_point")
    sam = MetaSamAdapter(client_for(transport), caller, storage, settings)

    await sam.segment_point(await panel(storage), Point(5000, 5000), "masks/obj")

    assert "<|point;x=383;y=255;w=384;h=256|>" in parts(seen[0])[0]["text"]
