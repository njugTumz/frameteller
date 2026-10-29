from datetime import timedelta

import pytest

from frameteller.application.budget import LimitBudgetGuard
from frameteller.application.errors import BudgetExceededError
from tests.fakes import FixedClock, InMemorySpendLedger


def guard(ledger: InMemorySpendLedger, clock: FixedClock | None = None) -> LimitBudgetGuard:
    return LimitBudgetGuard(ledger, clock or FixedClock(), per_project_usd=0.05, per_day_usd=0.08)


async def test_charges_within_limits_are_recorded() -> None:
    ledger = InMemorySpendLedger()
    await guard(ledger).charge("p1", 0.01, "panel")
    assert ledger.entries == [("p1", "2026-10-28", 0.01, "panel")]


async def test_budget_guard_blocks_project_overspend_before_spending() -> None:
    ledger = InMemorySpendLedger()
    g = guard(ledger)
    for _ in range(5):
        await g.charge("p1", 0.01, "panel")
    with pytest.raises(BudgetExceededError, match="project p1"):
        await g.charge("p1", 0.01, "panel")
    assert len(ledger.entries) == 5


async def test_budget_guard_blocks_daily_overspend_across_projects() -> None:
    ledger = InMemorySpendLedger()
    g = guard(ledger)
    for project_id in ("p1", "p2"):
        for _ in range(4):
            await g.charge(project_id, 0.01, "panel")
    with pytest.raises(BudgetExceededError, match="today"):
        await g.charge("p3", 0.01, "panel")


async def test_daily_limit_resets_the_next_day() -> None:
    ledger, clock = InMemorySpendLedger(), FixedClock()
    g = guard(ledger, clock)
    for project_id in ("p1", "p2"):
        for _ in range(4):
            await g.charge(project_id, 0.01, "panel")
    clock.current += timedelta(days=1)
    await g.charge("p3", 0.01, "panel")


async def test_negative_cost_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        await guard(InMemorySpendLedger()).charge("p1", -0.01, "refund")


def test_the_calendar_caps_launch_and_judging_days_in_utc_plus_4() -> None:
    from datetime import UTC, datetime

    from frameteller.application.budget import BudgetCalendar, parse_days
    from frameteller.application.lanes import Lane

    days = parse_days("2026-11-02:25, 2026-11-05:25")
    cal = BudgetCalendar(10, judge_per_day_usd=15, days_usd=days, utc_offset_hours=4)
    assert cal.day(datetime(2026, 11, 1, 19, 59, tzinfo=UTC)) == "2026-11-01"
    assert cal.day(datetime(2026, 11, 1, 20, 0, tzinfo=UTC)) == "2026-11-02"  # midnight in UTC+4
    assert (cal.cap("2026-11-02"), cal.cap("2026-11-03"), cal.cap("2026-11-05")) == (25, 10, 25)
    assert cal.cap("2026-11-03", Lane.JUDGE) == 15
    assert cal.pool("2026-11-03", Lane.JUDGE) == "2026-11-03.judge"
    with pytest.raises(ValueError, match="does not match format"):
        parse_days("Nov 2:25")


async def test_judges_are_charged_to_their_pool_without_a_project_cap() -> None:
    from frameteller.application.budget import BudgetCalendar
    from frameteller.application.lanes import Lane, lane_var

    ledger = InMemorySpendLedger()
    g = LimitBudgetGuard(ledger, FixedClock(), per_project_usd=0.01, calendar=BudgetCalendar(0.01, 0.05))
    token = lane_var.set(Lane.JUDGE)
    try:
        for _ in range(4):
            await g.charge("p1", 0.01, "panel")
        with pytest.raises(BudgetExceededError, match="judge"):
            await g.charge("p1", 0.02, "panel")
    finally:
        lane_var.reset(token)
    assert ledger.by_day == {"2026-10-28.judge": pytest.approx(0.04)}
