"""Dated limits (ADR 0016): more stories per visitor and a larger judge reserve on the judging days (UTC+4)."""

from datetime import UTC, datetime

import pytest

from frameteller.application.budget import BudgetCalendar, LimitBudgetGuard
from frameteller.application.errors import LimitReachedError, StudioFullError
from frameteller.application.judge import JudgeDesk, pass_var
from frameteller.application.lanes import Lane, lane_var
from frameteller.application.limits import DemoLimits, VisitorAllowance
from tests.fakes import FixedClock, InMemoryMediaStorage, InMemorySpendLedger, InMemoryVisitorQuota

JUDGING = {f"2026-11-0{d}": 5 for d in (5, 6, 7, 8)}
CALENDAR = BudgetCalendar(
    10, judge_per_day_usd=15, judge_days_usd={f"2026-11-0{d}": 25.0 for d in (5, 6, 7, 8)}, utc_offset_hours=4
)


def at(day: str, hour: int = 12) -> FixedClock:
    return FixedClock(datetime.fromisoformat(f"{day}T{hour:02d}:00:00+00:00").astimezone(UTC))


async def started(clock: FixedClock, limits: DemoLimits) -> int:
    allowance = VisitorAllowance(InMemoryVisitorQuota(), clock, limits, day=CALENDAR.day)
    for n in range(20):
        try:
            await allowance.take("visitor")
        except LimitReachedError:
            return n
    raise AssertionError("no limit")


async def test_visitors_get_five_stories_on_judging_days_and_three_otherwise() -> None:
    limits = DemoLimits(projects_per_visitor_per_day=3, projects_per_visitor_days=JUDGING)
    assert await started(at("2026-11-05"), limits) == 5
    assert await started(at("2026-11-08"), limits) == 5
    assert await started(at("2026-11-04"), limits) == 3
    # 22:00 UTC on Nov 4 is already Nov 5 in UTC+4.
    assert await started(at("2026-11-04", 22), limits) == 5
    assert limits.on("2026-11-06").messages()["projects"].startswith("You've started 5 stories today")


def test_the_judge_reserve_is_25_on_judging_days_and_15_otherwise() -> None:
    assert CALENDAR.cap("2026-11-05", Lane.JUDGE) == 25
    assert CALENDAR.cap("2026-11-08", Lane.JUDGE) == 25
    assert CALENDAR.cap("2026-11-04", Lane.JUDGE) == 15
    assert CALENDAR.cap("2026-11-09", Lane.JUDGE) == 15
    assert BudgetCalendar(10, judge_days_usd={"2026-11-05": 25.0}).cap("2026-11-05", Lane.JUDGE) == 0  # no judge pass


async def test_a_lowered_reserve_holds_judges_and_each_pass_spending_is_counted_apart() -> None:
    ledger, storage = InMemorySpendLedger(), InMemoryMediaStorage()
    desk = JudgeDesk(storage)
    guard = LimitBudgetGuard(ledger, at("2026-11-06"), per_project_usd=1, calendar=CALENDAR, desk=desk)
    lane, who = lane_var.set(Lane.JUDGE), pass_var.set("abc123")
    try:
        await guard.charge("p1", 0.5, "panel")
        assert ledger.by_day["2026-11-06.judge"] == 0.5
        assert ledger.by_day["2026-11-06.judge.abc123"] == 0.5
        await desk.set_reserve(0.6)
        with pytest.raises(StudioFullError):
            await guard.charge("p1", 0.2, "panel")
    finally:
        pass_var.reset(who)
        lane_var.reset(lane)
    assert await JudgeDesk(storage).reserve_override() == 0.6  # kept in storage: survives a restart
