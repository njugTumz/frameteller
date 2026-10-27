import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from openai import AsyncOpenAI

from frameteller.application.errors import InvalidModelOutputError, ModelRejectedError
from frameteller.application.ports import ImageRequest
from frameteller.domain import MediaRef, Size
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.local import LocalFileMediaStorage
from frameteller.infrastructure.meta.image import MetaImageAdapter
from frameteller.infrastructure.resilience import ModelCaller
from tests.fakes import InMemorySpendLedger
from tests.fixtures import THUMBNAIL, image, load, replay

Client = Callable[[httpx2.MockTransport], AsyncOpenAI]


def sent(request: httpx2.Request) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(request.content)
    return data


def status(code: int) -> dict[str, Any]:
    return {
        "method": "POST",
        "path": "/v1/responses",
        "status": code,
        "content_type": "application/json",
        "body": json.dumps({"error": {"message": f"HTTP {code}", "type": "error"}}),
    }


async def refs(storage: LocalFileMediaStorage) -> tuple[MediaRef, MediaRef]:
    mira = await storage.put("refs/mira.webp", image("ref_mira.webp"), "image/webp")
    cat = await storage.put("refs/cat.webp", image("ref_cat.webp"), "image/webp")
    return mira, cat


async def test_panel_with_references_is_stored_and_chainable(
    client_for: Client,
    caller: ModelCaller,
    storage: LocalFileMediaStorage,
    settings: Settings,
    ledger: InMemorySpendLedger,
) -> None:
    transport, seen = replay("image_generate")
    adapter = MetaImageAdapter(client_for(transport), caller, storage, settings)

    out = await adapter.generate(ImageRequest("a panel", "low", "panel", await refs(storage)), "panels/s1/r1")

    assert out.response_id == "resp_fixture2"
    assert out.size == Size(*THUMBNAIL)
    assert out.ref.key == "panels/s1/r1"
    assert (await storage.get(out.ref))[:4] == b"RIFF"  # webp bytes, decoded and persisted at once

    req = sent(seen[0])
    [tool] = req["tools"]
    assert tool == {
        "type": "image_generation",
        "enable_image_search": False,
        "enable_web_search": False,
        "enable_shell": False,
        "reasoning_strength": "low",
        "size": "1536x1024",
    }
    content = req["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "a panel"}
    assert [c["image_url"][:23] for c in content[1:]] == ["data:image/webp;base64,"] * 2

    [usage] = ledger.usage
    assert usage.cost_usd == 0.01
    assert usage.cached_tokens == 3968


async def test_reference_sheet_is_square_and_final_quality(
    client_for: Client, caller: ModelCaller, storage: LocalFileMediaStorage, settings: Settings
) -> None:
    transport, seen = replay("image_generate")
    adapter = MetaImageAdapter(client_for(transport), caller, storage, settings)

    await adapter.generate(ImageRequest("Mira, turnaround", "high", "square"), "projects/p1/characters/mira/reference")

    [tool] = sent(seen[0])["tools"]
    assert (tool["size"], tool["reasoning_strength"]) == ("1024x1024", "high")
    assert len(sent(seen[0])["input"][0]["content"]) == 1


async def test_edit_chains_on_the_previous_response(
    client_for: Client, caller: ModelCaller, storage: LocalFileMediaStorage, settings: Settings
) -> None:
    transport, seen = replay("image_edit")
    adapter = MetaImageAdapter(client_for(transport), caller, storage, settings)

    out = await adapter.edit("resp_fixture2", "Make her raincoat red.", "low", "panels/s1/r2")

    req = sent(seen[0])
    assert req["previous_response_id"] == "resp_fixture2"
    assert req["input"] == "Make her raincoat red."
    assert out.response_id == "resp_fixture6"
    assert out.ref.key == "panels/s1/r2"


async def test_rate_limit_is_retried(
    client_for: Client,
    caller: ModelCaller,
    storage: LocalFileMediaStorage,
    settings: Settings,
    ledger: InMemorySpendLedger,
) -> None:
    transport, seen = replay([status(429), status(503), *load("image_edit")])
    adapter = MetaImageAdapter(client_for(transport), caller, storage, settings)

    out = await adapter.edit("resp_fixture2", "red coat", "low", "panels/s1/r2")

    assert out.response_id == "resp_fixture6"
    assert len(seen) == 3
    assert [u.ok for u in ledger.usage] == [False, False, True]
    assert sum(u.cost_usd for u in ledger.usage) == 0.01  # failed attempts are not billed


async def test_bad_request_is_not_retried(
    client_for: Client, caller: ModelCaller, storage: LocalFileMediaStorage, settings: Settings
) -> None:
    transport, seen = replay([status(400)])
    adapter = MetaImageAdapter(client_for(transport), caller, storage, settings)

    with pytest.raises(ModelRejectedError):
        await adapter.edit("resp_fixture2", "red coat", "low", "panels/s1/r2")
    assert len(seen) == 1


async def test_response_without_an_image_is_invalid_output(
    client_for: Client, caller: ModelCaller, storage: LocalFileMediaStorage, settings: Settings
) -> None:
    ex = load("image_edit")[0]
    b = json.loads(ex["body"])
    b["output"] = [o for o in b["output"] if o["type"] != "image_generation_call"]
    transport, _ = replay([{**ex, "body": json.dumps(b)}])
    adapter = MetaImageAdapter(client_for(transport), caller, storage, settings)

    with pytest.raises(InvalidModelOutputError):
        await adapter.edit("resp_fixture2", "red coat", "low", "panels/s1/r2")
