"""Budget policy: per-project and per-day spend limits (CLAUDE.md section 6, cost guardrails).

The daily cap follows a calendar in the team's time zone (UTC+4): higher on launch and judging days. Judges
spend from their own reserved pool, which the public cap can never consume (ADR 0016).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from frameteller.application.errors import BudgetExceededError, StudioFullError
from frameteller.application.lanes import Lane, current_lane
from frameteller.application.ports import Clock, SpendLedger


@dataclass(frozen=True, slots=True)
class BudgetCalendar:
    """The daily caps: `per_day_usd` on most days, `days_usd` on the dates it names, `judge_per_day_usd` for judges.

    A day is a date at `utc_offset_hours` (4: the team's midnight), so a cap never changes mid-evening.
    """

    per_day_usd: float
    judge_per_day_usd: float = 0.0
    days_usd: Mapping[str, float] = field(default_factory=dict)
    utc_offset_hours: float = 0.0

    def day(self, now: datetime) -> str:
        return now.astimezone(timezone(timedelta(hours=self.utc_offset_hours))).date().isoformat()

    def cap(self, day: str, lane: Lane = Lane.PUBLIC) -> float:
        if lane is Lane.JUDGE:
            return self.judge_per_day_usd
        return self.days_usd.get(day, self.per_day_usd)

    @staticmethod
    def pool(day: str, lane: Lane = Lane.PUBLIC) -> str:
        """The ledger's day key: the judges' pool is counted apart from the public one."""
        return f"{day}.judge" if lane is Lane.JUDGE else day


def parse_days(text: str) -> dict[str, float]:
    """`2026-11-02:25,2026-11-05:25` -> {"2026-11-02": 25.0, ...}. Raises ValueError on a malformed entry."""
    days: dict[str, float] = {}
    for entry in (e.strip() for e in text.split(",")):
        if not entry:
            continue
        day, _, usd = entry.partition(":")
        days[datetime.strptime(day.strip(), "%Y-%m-%d").date().isoformat()] = float(usd)
    return days


class LimitBudgetGuard:
    """Implements BudgetGuard. Checks both limits before recording, so a refused call costs nothing."""

    def __init__(
        self,
        ledger: SpendLedger,
        clock: Clock,
        *,
        per_project_usd: float,
        per_day_usd: float | None = None,
        calendar: BudgetCalendar | None = None,
    ) -> None:
        if (per_day_usd is None) == (calendar is None):
            raise ValueError("give per_day_usd or a calendar")
        self._ledger, self._clock = ledger, clock
        self._per_project = per_project_usd
        self._calendar = calendar or BudgetCalendar(per_day_usd or 0.0)
        self._lock = asyncio.Lock()

    async def charge(self, project_id: str, cost_usd: float, what: str) -> None:
        if cost_usd < 0:
            raise ValueError("cost must not be negative")
        lane = current_lane()
        day = self._calendar.day(self._clock.now())
        pool, cap = self._calendar.pool(day, lane), self._calendar.cap(day, lane)
        async with self._lock:
            project_total = await self._ledger.spent_by_project(project_id) + cost_usd
            day_total = await self._ledger.spent_on_day(pool) + cost_usd
            # Judges' projects have no per-project cap: their reserved pool is the limit.
            if lane is Lane.PUBLIC and project_total > self._per_project:
                raise BudgetExceededError(
                    f"{what}: project {project_id} would reach ${project_total:.2f} (limit ${self._per_project:.2f})"
                )
            if day_total > cap:
                raise StudioFullError(f"{what}: today ({pool}) would reach ${day_total:.2f} (limit ${cap:.2f})")
            await self._ledger.record(project_id, pool, cost_usd, what)
