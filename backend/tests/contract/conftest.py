"""Contract tests: real adapters and the real OpenAI SDK against recorded Meta responses. No network."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx2
import pytest
from openai import AsyncOpenAI

from frameteller.infrastructure.config import Settings, load_settings
from frameteller.infrastructure.local import LocalFileMediaStorage
from frameteller.infrastructure.meta import meta_client
from frameteller.infrastructure.resilience import Breakers, ModelCaller
from tests.fakes import InMemorySpendLedger

FAKE_KEY = "LLM_test_not_a_real_key_000000"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/contract/" in item.nodeid:
            item.add_marker(pytest.mark.contract)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.chdir(tmp_path)  # never read a developer's .env
    for name in ("MODEL_API_KEY", "APP_ENV", "DIRECTOR_MODEL"):
        monkeypatch.delenv(name, raising=False)
    return load_settings(model_api_key=FAKE_KEY, app_env="local", local_storage_dir=tmp_path)


@pytest.fixture
def ledger() -> InMemorySpendLedger:
    return InMemorySpendLedger()


@pytest.fixture
def caller(ledger: InMemorySpendLedger) -> ModelCaller:
    async def no_sleep(_: float) -> None:
        return None

    return ModelCaller(ledger, Breakers(), sleep=no_sleep)


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileMediaStorage:
    return LocalFileMediaStorage(tmp_path)


@pytest.fixture
def client_for(settings: Settings) -> Callable[[httpx2.MockTransport], AsyncOpenAI]:
    def make(transport: httpx2.MockTransport) -> AsyncOpenAI:
        return meta_client(settings, httpx2.AsyncClient(transport=transport))

    return make
