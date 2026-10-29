"""Whether the studio takes new work right now: paused by the kill switch, or full for today."""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.application.budget import BudgetCalendar
from frameteller.application.lanes import Lane, current_lane
from frameteller.application.limits import DemoLimits
from frameteller.application.ports import Clock, SpendLedger

# Below the cheapest model call: past this the day's cap is as good as reached.
FULL_MARGIN_USD = 0.01


@dataclass(frozen=True, slots=True)
class StudioStatus:
    paused: bool
    full: bool  # the global daily spend cap is reached; shared storyboards still open
    limits: DemoLimits
    judge: bool = False  # this request carries a valid judge pass
    day: str = ""  # the budget day (UTC+4)
    cap_usd: float = 0.0  # today's cap for this lane
    spent_usd: float = 0.0


class GetStudioStatus:
    def __init__(
        self,
        ledger: SpendLedger,
        clock: Clock,
        *,
        paused: bool,
        limits: DemoLimits,
        per_day_usd: float | None = None,
        calendar: BudgetCalendar | None = None,
    ) -> None:
        self._ledger, self._clock = ledger, clock
        self._calendar = calendar or BudgetCalendar(per_day_usd or 0.0)
        self._paused, self._limits = paused, limits

    async def execute(self, lane: Lane | None = None) -> StudioStatus:
        """For the caller's lane: a judge sees the judges' pool, which stays open when the public one is full."""
        lane = lane or current_lane()
        day = self._calendar.day(self._clock.now())
        spent = await self._ledger.spent_on_day(self._calendar.pool(day, lane))
        cap = self._calendar.cap(day, lane)
        full = spent >= cap - FULL_MARGIN_USD
        return StudioStatus(self._paused, full, self._limits, lane is Lane.JUDGE, day, cap, round(spent, 4))
