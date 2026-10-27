"""MetaImageAdapter: panels and reference sheets with Muse Image on the Responses API (ADR 0003, 0005)."""

from __future__ import annotations

import base64
from typing import Any

from openai import AsyncOpenAI

from frameteller.application.errors import InvalidModelOutputError
from frameteller.application.ports import ImageRequest, MediaStoragePort, Quality, StoredImage
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.meta.images import data_url, inspect_image
from frameteller.infrastructure.pricing import IMAGE_USD
from frameteller.infrastructure.resilience import ModelCaller, RetryPolicy, Usage


def image_tool(size: str, quality: Quality) -> dict[str, Any]:
    # Search stays off so renders never pull in real likenesses or copyrighted designs (hackathon rights rule).
    return {
        "type": "image_generation",
        "enable_image_search": False,
        "enable_web_search": False,
        "enable_shell": False,
        "reasoning_strength": quality,
        "size": size,
    }


class MetaImageAdapter:
    """ImageGenerationPort. Model output is decoded and stored at once; only our ref leaves this class."""

    def __init__(self, client: AsyncOpenAI, caller: ModelCaller, storage: MediaStoragePort, settings: Settings) -> None:
        self._client, self._caller, self._storage, self._settings = client, caller, storage, settings
        self._policy = RetryPolicy(attempts=settings.retry_attempts, timeout_s=settings.image_timeout_s)

    async def generate(self, request: ImageRequest, store_as: str) -> StoredImage:
        size = self._settings.image_panel_size if request.aspect == "panel" else self._settings.image_reference_size
        content: list[dict[str, Any]] = [{"type": "input_text", "text": request.prompt}]
        for ref in request.references:
            data = await self._storage.get(ref)
            _, content_type = inspect_image(data)
            content.append({"type": "input_image", "image_url": data_url(data, content_type)})
        kwargs = {"input": [{"role": "user", "content": content}], "tools": [image_tool(size, request.quality)]}
        return await self._render("generate", kwargs, store_as)

    async def edit(self, previous_response_id: str, prompt: str, quality: Quality, store_as: str) -> StoredImage:
        """Chained appearance edit: send only the change (CLAUDE.md section 5)."""
        kwargs = {
            "previous_response_id": previous_response_id,
            "input": prompt,
            "tools": [image_tool(self._settings.image_panel_size, quality)],
        }
        return await self._render("edit", kwargs, store_as)

    async def _render(self, operation: str, kwargs: dict[str, Any], store_as: str) -> StoredImage:
        model = self._settings.image_model

        async def call() -> tuple[tuple[bytes, str], Usage]:
            response = await self._client.responses.create(model=model, **kwargs)
            for item in response.output:
                if item.type == "image_generation_call" and item.result:
                    u = response.usage
                    cached = u.input_tokens_details.cached_tokens if u and u.input_tokens_details else None
                    usage = Usage(IMAGE_USD, u.input_tokens if u else None, u.output_tokens if u else None, cached)
                    return (base64.b64decode(item.result), response.id), usage
            raise InvalidModelOutputError(model, f"response {response.id} has no image")

        data, response_id = await self._caller.call(model, operation, call, self._policy)
        size, content_type = inspect_image(data)
        ref = await self._storage.put(store_as, data, content_type)
        return StoredImage(ref, response_id, size)
