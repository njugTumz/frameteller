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
