"""Whether the studio takes new work right now: paused by the kill switch, or full for today."""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.application.limits import DemoLimits
from frameteller.application.ports import Clock, SpendLedger

# Below the cheapest model call: past this the day's cap is as good as reached.
FULL_MARGIN_USD = 0.01


@dataclass(frozen=True, slots=True)
class StudioStatus:
    paused: bool
    full: bool  # the global daily spend cap is reached; shared storyboards still open
    limits: DemoLimits


class GetStudioStatus:
    def __init__(
        self, ledger: SpendLedger, clock: Clock, *, per_day_usd: float, paused: bool, limits: DemoLimits
    ) -> None:
        self._ledger, self._clock = ledger, clock
        self._per_day, self._paused, self._limits = per_day_usd, paused, limits

    async def execute(self) -> StudioStatus:
        spent = await self._ledger.spent_on_day(self._clock.now().date().isoformat())
        return StudioStatus(self._paused, spent >= self._per_day - FULL_MARGIN_USD, self._limits)
