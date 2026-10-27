"""Budget policy: per-project and per-day spend limits (CLAUDE.md section 6, cost guardrails)."""

from __future__ import annotations

import asyncio

from frameteller.application.errors import BudgetExceededError
from frameteller.application.ports import Clock, SpendLedger


class LimitBudgetGuard:
    """Implements BudgetGuard. Checks both limits before recording, so a refused call costs nothing."""

    def __init__(self, ledger: SpendLedger, clock: Clock, *, per_project_usd: float, per_day_usd: float) -> None:
        self._ledger, self._clock = ledger, clock
        self._per_project, self._per_day = per_project_usd, per_day_usd
        self._lock = asyncio.Lock()

    async def charge(self, project_id: str, cost_usd: float, what: str) -> None:
        if cost_usd < 0:
            raise ValueError("cost must not be negative")
        day = self._clock.now().date().isoformat()
        async with self._lock:
            project_total = await self._ledger.spent_by_project(project_id) + cost_usd
            day_total = await self._ledger.spent_on_day(day) + cost_usd
            if project_total > self._per_project:
                raise BudgetExceededError(
                    f"{what}: project {project_id} would reach ${project_total:.2f} (limit ${self._per_project:.2f})"
                )
            if day_total > self._per_day:
                raise BudgetExceededError(f"{what}: today would reach ${day_total:.2f} (limit ${self._per_day:.2f})")
            await self._ledger.record(project_id, day, cost_usd, what)
