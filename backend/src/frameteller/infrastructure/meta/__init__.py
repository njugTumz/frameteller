"""Adapters for Meta's Model API (CLAUDE.md section 5). The only place that talks to Meta."""

from __future__ import annotations

import httpx2
from openai import AsyncOpenAI

from frameteller.infrastructure.config import Settings


def meta_client(settings: Settings, http_client: httpx2.AsyncClient | None = None) -> AsyncOpenAI:
    """OpenAI-compatible client. The key is passed explicitly; SDK retries are off (resilience.py retries)."""
    return AsyncOpenAI(
        api_key=settings.model_api_key.get_secret_value(),
        base_url=settings.meta_base_url,
        max_retries=0,
        http_client=http_client,
    )
