"""Judges wake Muse Glimmer (ADR 0020): the wake-up, the lease that follows judge activity, and the daily caps."""

from datetime import timedelta

import pytest

from frameteller.application.glimmer_wakeup import JudgeGlimmer, WakePolicy
from tests.fakes import FakeGlimmerLease, FakeGlimmerWarmer, FixedClock, InMemoryMediaStorage


class World:
    def __init__(self, policy: WakePolicy | None = None, **warmer: object) -> None:
        self.clock = FixedClock()
        self.lease = FakeGlimmerLease(self.clock)
        self.warmer = FakeGlimmerWarmer(self.clock, **warmer)  # type: ignore[arg-type]
        self.storage = InMemoryMediaStorage()
        self.activity: list[float] = []  # seconds after a keeper tick at which a judge acts again
        self.glimmer = JudgeGlimmer(
            self.lease,
            self.warmer,
            self.storage,
            self.clock,
            lambda now: now.date().isoformat(),
            policy or WakePolicy(),
            sleep=self.sleep,
        )

    async def sleep(self, seconds: float) -> None:
        self.clock.current += timedelta(seconds=seconds)
        while self.activity and self.activity[0] <= 0:
            self.activity.pop(0)
            await self.glimmer.judge_active()
        self.activity = [a - seconds for a in self.activity]


async def test_a_judge_wakes_glimmer_and_the_lease_ends_five_minutes_after_the_last_activity() -> None:
    w = World()
    started = w.clock.now()
    assert await w.glimmer.judge_active() is True
    assert await w.glimmer.judge_active() is False  # already waking: one wake-up
    await w.glimmer.wait()
    assert w.warmer.wakes == 1
    # The last activity was at `started` (before the 3-minute cold start): the lease ends 5 minutes after it.
    assert w.lease.held
    assert w.lease.held[-1] == started + timedelta(minutes=5)
    assert await w.lease.warm_until() is None  # and it has run out
    today = await w.glimmer.today()
    assert (today.wakes, today.last_cold_start_s) == (1, 180.0)
    # Estimated: 5 minutes from the request to the end of the lease, plus 5 idle minutes before Modal scales down.
    assert today.estimated_usd == pytest.approx(10 / 60 * 3.95, abs=0.01)


async def test_judges_who_keep_working_keep_the_lease_and_glimmer_gets_pinged() -> None:
    w = World()
    w.activity = [0, 120, 240, 360, 480, 600]  # a judge acts every 2 minutes for 10 minutes
    started = w.clock.now()
    await w.glimmer.judge_active()
    await w.glimmer.wait()
    last_activity = w.lease.held[-1] - timedelta(minutes=5)
    assert last_activity >= started + timedelta(minutes=10)
    assert w.warmer.pings >= 2  # every 4 minutes, so Modal keeps the container up
    assert w.warmer.wakes == 1


async def test_already_warm_needs_no_wake_up() -> None:
    w = World()
    w.lease.until = w.clock.now() + timedelta(minutes=10)  # the warm-up script holds it
    assert await w.glimmer.judge_active() is False
    assert w.warmer.wakes == 0


async def test_at_most_ten_wake_ups_a_day() -> None:
    w = World(WakePolicy(usd_per_day=100), cold_start_s=1)  # the count cap alone (5 USD stops it after 7)
    for _ in range(10):
        assert await w.glimmer.judge_active() is True
        await w.glimmer.wait()
        w.clock.current += timedelta(minutes=10)  # the lease ran out; judges come back
    assert await w.glimmer.judge_active() is False  # judges get Spark for the rest of the day
    assert w.warmer.wakes == 10
    w.clock.current += timedelta(days=1)
    assert await w.glimmer.judge_active() is True  # a new day


async def test_the_spend_guard_stops_wake_ups_and_ends_a_running_one() -> None:
    w = World(WakePolicy(usd_per_day=1.0))  # 1 USD is about 15 minutes of H100
    w.activity = [60 * n for n in range(0, 60, 2)]  # judges active for an hour
    await w.glimmer.judge_active()
    await w.glimmer.wait()
    assert await w.lease.warm_until() is None  # revoked at the guard, long before the hour was over
    today = await w.glimmer.today()
    assert 1.0 <= today.estimated_usd < 1.2
    assert await w.glimmer.judge_active() is False  # no more wake-ups today


async def test_a_failed_wake_up_leaves_reviews_with_spark() -> None:
    w = World(fail=True)
    await w.glimmer.judge_active()
    await w.glimmer.wait()
    assert w.lease.held == []
    assert (await w.glimmer.today()).wakes == 1  # it still counts toward the cap


async def test_glimmer_that_stops_answering_loses_the_lease() -> None:
    w = World()
    w.activity = [60 * n for n in range(0, 20)]
    w.warmer.ping_fails = True
    await w.glimmer.judge_active()
    await w.glimmer.wait()
    assert await w.lease.warm_until() is None
