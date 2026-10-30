"""Judges wake Muse Glimmer (ADR 0020); public visitors never do."""

import asyncio
from collections.abc import Callable
from datetime import timedelta

from frameteller.application.glimmer_wakeup import JudgeGlimmer
from tests.fakes import FakeGlimmerLease, FakeGlimmerWarmer, FixedClock
from tests.interface.conftest import Api

TOKEN = "judge-token-for-tests-0123456789abcdef"
ADMIN = "admin-token-for-tests-0123456789abcdef"
ME = {"X-Visitor-Id": "browser-0123456789abcdef"}


RELEASE = asyncio.Event()


def with_glimmer(api: Api) -> FakeGlimmerWarmer:
    clock = FixedClock()
    warmer = FakeGlimmerWarmer(clock)
    RELEASE.clear()

    async def sleep(seconds: float) -> None:
        """The keeper holds the lease until the test lets time pass, then its ticks pass on the fake clock."""
        await RELEASE.wait()
        clock.current += timedelta(seconds=seconds)

    api.container.judge_glimmer = JudgeGlimmer(
        FakeGlimmerLease(clock), warmer, api.fakes.storage, clock, lambda now: now.date().isoformat(), sleep=sleep
    )
    return warmer


async def test_public_visitors_never_wake_glimmer(make_api: Callable[..., Api]) -> None:
    api = make_api(judge_token=TOKEN)
    warmer = with_glimmer(api)
    await api.client.get("/status", headers=ME)
    await api.client.post("/projects", json={"title": "A public story"}, headers=ME)
    await api.client.get("/projects/p1", headers=ME)
    assert api.container.judge_glimmer is not None
    RELEASE.set()
    await api.container.judge_glimmer.wait()
    assert warmer.wakes == 0


async def test_a_judge_pass_wakes_glimmer_once_and_the_admin_sees_it(make_api: Callable[..., Api]) -> None:
    api = make_api(judge_token=TOKEN, admin_token=ADMIN)
    warmer = with_glimmer(api)
    await api.client.post("/judge", json={"token": TOKEN})  # sets the cookie; this request had none yet
    assert warmer.wakes == 0
    await api.client.get("/status")
    await api.client.post("/projects", json={"title": "A judge's story"}, headers=ME)
    assert api.container.judge_glimmer is not None
    RELEASE.set()
    await api.container.judge_glimmer.wait()
    assert warmer.wakes == 1

    api.client.cookies.clear()  # the admin's own browser, without a judge pass
    overview = (await api.client.get("/admin/overview", headers={"Authorization": f"Bearer {ADMIN}"})).json()
    glimmer = overview["judge_glimmer"]
    assert (glimmer["wakes"], glimmer["wakes_cap"], glimmer["usd_cap"]) == (1, 10, 5.0)
    assert glimmer["last_cold_start_s"] == 180.0
    assert glimmer["estimated_usd"] > 0


async def test_without_glimmer_the_overview_says_so(make_api: Callable[..., Api]) -> None:
    api = make_api(judge_token=TOKEN, admin_token=ADMIN)
    overview = (await api.client.get("/admin/overview", headers={"Authorization": f"Bearer {ADMIN}"})).json()
    assert overview["judge_glimmer"] is None
    assert (await api.client.post("/internal/glimmer/judge-wake")).status_code == 404
