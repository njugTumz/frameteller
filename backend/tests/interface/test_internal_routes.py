"""The operator routes over HTTP: only the Glimmer token may grant or revoke the lease, or act as a judge to wake
Glimmer (and that counts toward the same daily caps)."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest

from frameteller.application.glimmer_wakeup import JudgeGlimmer, WakePolicy
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.review import GlimmerLease
from frameteller.interface.app import create_app
from tests.fakes import FakeGlimmerWarmer, FixedClock
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


def waking(settings: Settings, fakes: Fakes, policy: WakePolicy | None = None) -> tuple[httpx2.AsyncClient, Any]:
    """The judge-wake route over a JudgeGlimmer whose keeper's ticks pass on the fake clock."""
    clock = FixedClock()
    lease, warmer = GlimmerLease(fakes.storage, clock), FakeGlimmerWarmer(clock, cold_start_s=60)

    async def sleep(seconds: float) -> None:
        clock.current += timedelta(seconds=seconds)

    glimmer = JudgeGlimmer(lease, warmer, fakes.storage, clock, lambda now: now.date().isoformat(), policy, sleep)
    container = replace(build(settings, fakes), glimmer_lease=lease, judge_glimmer=glimmer)
    c = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=create_app(container=container)), base_url="http://test")
    return c, SimpleNamespace(clock=clock, warmer=warmer, glimmer=glimmer)


@pytest.mark.parametrize("header", [None, "Bearer wrong", f"Basic {TOKEN}"])
async def test_without_the_token_the_judge_wake_is_refused(
    make_settings: Any, fakes: Fakes, header: str | None
) -> None:
    c, w = waking(make_settings(**GLIMMER), fakes)
    headers = {"Authorization": header} if header else {}
    assert (await c.post("/internal/glimmer/judge-wake", headers=headers)).status_code == 401
    await w.glimmer.wait()
    assert w.warmer.wakes == 0
    assert (await w.glimmer.today()).wakes == 0  # a refused call never counts toward the cap


async def wake_until_refused(c: httpx2.AsyncClient, w: Any) -> int:
    started = 0
    for _ in range(20):
        r = await c.post("/internal/glimmer/judge-wake", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200
        if not r.json()["started"]:
            return started
        started += 1
        await w.glimmer.wait()
        w.clock.current += timedelta(minutes=10)  # the lease ran out
    return started


async def test_the_judge_wake_counts_toward_the_ten_wake_ups_a_day(make_settings: Any, fakes: Fakes) -> None:
    c, w = waking(make_settings(**GLIMMER), fakes, WakePolicy(usd_per_day=100))
    assert await wake_until_refused(c, w) == 10
    assert w.warmer.wakes == 10


async def test_the_judge_wake_stops_at_the_five_dollar_guard(make_settings: Any, fakes: Fakes) -> None:
    c, w = waking(make_settings(**GLIMMER), fakes)
    assert await wake_until_refused(c, w) < 10
    assert (await w.glimmer.today()).estimated_usd >= 5.0
