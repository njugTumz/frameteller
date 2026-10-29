"""The warm-up script's Glimmer lease over HTTP: only the Glimmer token may grant or revoke it."""

from dataclasses import replace
from typing import Any

import httpx2
import pytest

from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.review import GlimmerLease
from frameteller.interface.app import create_app
from tests.fakes import FixedClock
from tests.interface.conftest import Fakes, build

TOKEN = "test-endpoint-token"
GLIMMER = {"reviewer": "screen", "glimmer_base_url": "https://glimmer.test/v1", "glimmer_api_key": TOKEN}


def client(settings: Settings, fakes: Fakes, *, gated: bool = True) -> tuple[httpx2.AsyncClient, Any]:
    container = build(settings, fakes)
    if gated:
        container = replace(container, glimmer_lease=GlimmerLease(fakes.storage, FixedClock()))
    app = create_app(container=container)
    return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test"), container


async def test_the_glimmer_token_grants_and_revokes_the_lease(make_settings: Any, fakes: Fakes) -> None:
    c, container = client(make_settings(**GLIMMER), fakes)
    r = await c.post("/internal/glimmer/lease", json={"minutes": 10}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert r.json()["warm_until"] == "2026-10-28T12:10:00+00:00"
    assert await container.glimmer_lease.warm_until() is not None
    r = await c.delete("/internal/glimmer/lease", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.json() == {"warm_until": None}
    assert await container.glimmer_lease.warm_until() is None


@pytest.mark.parametrize("header", [None, "Bearer wrong", f"Basic {TOKEN}"])
async def test_without_the_token_the_lease_is_refused(make_settings: Any, fakes: Fakes, header: str | None) -> None:
    c, container = client(make_settings(**GLIMMER), fakes)
    headers = {"Authorization": header} if header else {}
    r = await c.post("/internal/glimmer/lease", json={"minutes": 10}, headers=headers)
    assert r.status_code == 401
    assert await container.glimmer_lease.warm_until() is None


async def test_with_spark_alone_there_is_no_lease_route(make_settings: Any, fakes: Fakes) -> None:
    c, _ = client(make_settings(), fakes, gated=False)
    r = await c.post("/internal/glimmer/lease", json={"minutes": 10}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 404


async def test_a_lease_longer_than_half_an_hour_is_refused(make_settings: Any, fakes: Fakes) -> None:
    c, _ = client(make_settings(**GLIMMER), fakes)
    r = await c.post("/internal/glimmer/lease", json={"minutes": 90}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 422


def test_screen_and_fallback_are_gated_by_default_and_spark_is_not(make_settings: Any, fakes: Fakes) -> None:
    from frameteller.interface.container import glimmer_lease

    assert glimmer_lease(make_settings(**GLIMMER), fakes.storage) is not None
    assert glimmer_lease(make_settings(**{**GLIMMER, "reviewer": "fallback"}), fakes.storage) is not None
    assert glimmer_lease(make_settings(**GLIMMER, glimmer_only_when_warm=False), fakes.storage) is None
    assert glimmer_lease(make_settings(), fakes.storage) is None
