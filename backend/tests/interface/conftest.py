"""Interface tests: the real app, routes and composition root (wire) over in-memory fakes. No network."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI

from frameteller.domain import Project
from frameteller.infrastructure.config import Settings, load_settings
from frameteller.interface.app import create_app
from frameteller.interface.container import Container, wire
from tests.builders import project
from tests.fakes import (
    FakeDirector,
    FakeImageGeneration,
    FakeSegmentation,
    FakeSpeechToText,
    InMemoryMediaStorage,
    InMemoryProjectRepository,
    InMemorySpendLedger,
    SequentialIds,
)

FAKE_KEY = "LLM_test_not_a_real_key_000000"


@dataclass
class Fakes:
    repo: InMemoryProjectRepository
    storage: InMemoryMediaStorage
    director: FakeDirector = field(default_factory=FakeDirector)
    sam: FakeSegmentation = field(default_factory=FakeSegmentation)
    speech: FakeSpeechToText = field(default_factory=FakeSpeechToText)
    ledger: InMemorySpendLedger = field(default_factory=InMemorySpendLedger)
    ready: bool = True

    def __post_init__(self) -> None:
        self.images = FakeImageGeneration(self.storage)


@pytest.fixture
def make_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[..., Settings]:
    monkeypatch.chdir(tmp_path)  # never read a developer's .env
    for name in ("MODEL_API_KEY", "APP_ENV", "DIRECTOR_MODEL", "ALLOWED_ORIGINS"):
        monkeypatch.delenv(name, raising=False)

    def make(**overrides: Any) -> Settings:
        return load_settings(model_api_key=FAKE_KEY, local_storage_dir=tmp_path, **overrides)

    return make


@pytest.fixture
def fakes() -> Fakes:
    storage = InMemoryMediaStorage()
    storage.files["refs/mira.webp"] = (b"mira-ref", "image/webp")
    storage.files["refs/cat.webp"] = (b"cat-ref", "image/webp")
    return Fakes(InMemoryProjectRepository(project()), storage)


def build(settings: Settings, f: Fakes) -> Container:
    async def storage_check() -> None:
        if not f.ready:
            raise OSError("disk full")

    return wire(
        settings,
        repo=f.repo,
        storage=f.storage,
        director=f.director,
        images=f.images,
        segmentation=f.sam,
        speech=f.speech,
        ledger=f.ledger,
        ids=SequentialIds("id"),
        readiness={"storage": storage_check},
    )


@dataclass
class Api:
    app: FastAPI
    container: Container
    client: httpx2.AsyncClient
    fakes: Fakes

    def project(self, project_id: str = "p1") -> Project:
        return self.fakes.repo.peek(project_id)

    async def settle(self) -> None:
        """Run queued jobs to completion (renders, pre-segmentation, cast sheets)."""
        await self.container.jobs.join()


@pytest.fixture
def make_api(make_settings: Callable[..., Settings], fakes: Fakes) -> Callable[..., Api]:
    def make(**settings: Any) -> Api:
        container = build(make_settings(**settings), fakes)
        app = create_app(container=container)
        client = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test")
        return Api(app, container, client, fakes)

    return make


@pytest.fixture
async def api(make_api: Callable[..., Api]) -> AsyncIterator[Api]:
    a = make_api()
    yield a
    await a.client.aclose()


class WsClient:
    """Drives one ASGI WebSocket connection directly: no server, no network."""

    def __init__(self, app: FastAPI, path: str, headers: dict[str, str] | None = None) -> None:
        self._to_app: asyncio.Queue[MutableMapping[str, Any]] = asyncio.Queue()
        self._from_app: asyncio.Queue[MutableMapping[str, Any]] = asyncio.Queue()
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "scheme": "ws",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": ("127.0.0.1", 50000),
            "server": ("test", 80),
            "subprotocols": [],
        }
        self.task = asyncio.create_task(app(scope, self._to_app.get, self._from_app.put))
        self.close_code: int | None = None

    async def connect(self) -> bool:
        await self._to_app.put({"type": "websocket.connect"})
        message = await self._next()
        if message["type"] == "websocket.close":
            self.close_code = message.get("code", 1000)
            return False
        return bool(message["type"] == "websocket.accept")

    async def send_json(self, data: Any) -> None:
        await self._to_app.put({"type": "websocket.receive", "text": json.dumps(data)})

    async def send_bytes(self, data: bytes) -> None:
        await self._to_app.put({"type": "websocket.receive", "bytes": data})

    async def disconnect(self) -> None:
        await self._to_app.put({"type": "websocket.disconnect", "code": 1000})

    async def receive(self) -> dict[str, Any] | None:
        """The next JSON event, or None once the server closed the socket."""
        message = await self._next()
        if message["type"] == "websocket.close":
            self.close_code = message.get("code", 1000)
            return None
        data: dict[str, Any] = json.loads(message["text"])
        return data

    async def until(self, *types: str, limit: int = 200) -> list[dict[str, Any]]:
        """Collect events until every type in `types` has been seen."""
        seen: list[dict[str, Any]] = []
        missing = set(types)
        while missing and len(seen) < limit:
            event = await self.receive()
            if event is None:
                break
            seen.append(event)
            missing.discard(event["type"])
        return seen

    async def _next(self) -> MutableMapping[str, Any]:
        return await asyncio.wait_for(self._from_app.get(), 5)

    async def finish(self) -> None:
        if not self.task.done():
            await self.disconnect()
        await asyncio.wait_for(self.task, 5)
