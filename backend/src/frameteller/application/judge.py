"""Judge passes (ADR 0016): one private link, a pass per browser, a story limit per pass, and the admin's controls.

The link's token is never used up: every browser that opens it gets its own pass (its own id in the signed
cookie), so any number of judges can use one link. The interface puts the pass id in `pass_var` with the lane.

The desk keeps one small document (`admin/judge.json`, never served by /media): the passes seen per day, and the
reserve the admin set from the admin page, so a lower reserve holds across restarts without a redeploy.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from frameteller.application.ports import Clock, MediaStoragePort, SpendLedger, VisitorQuota
from frameteller.domain import MediaRef

pass_var: ContextVar[str | None] = ContextVar("judge_pass", default=None)
DOCUMENT = "admin/judge.json"
PASS_PREFIX = "judge-pass:"  # quota and ledger keys of a pass, apart from visitors and projects


def current_pass() -> str | None:
    return pass_var.get()


def pass_key(pass_id: str) -> str:
    return f"{PASS_PREFIX}{pass_id}"


def pass_pool(day: str, pass_id: str) -> str:
    """The ledger's day key for one pass's spending, counted beside (never inside) the judges' pool."""
    return f"{day}.judge.{pass_id}"


@dataclass(frozen=True, slots=True)
class PassActivity:
    pass_id: str
    first_seen: str  # ISO 8601
    stories_today: int
    spent_today_usd: float


class JudgeDesk:
    """The passes seen and the admin's reserve override, in one document. One replica (ADR 0009): a lock suffices."""

    def __init__(self, storage: MediaStoragePort) -> None:
        self._storage = storage
        self._lock = asyncio.Lock()
        self._cache: dict[str, Any] | None = None

    async def _read(self) -> dict[str, Any]:
        if self._cache is None:
            ref = MediaRef(DOCUMENT)
            self._cache = json.loads(await self._storage.get(ref)) if await self._storage.exists(ref) else {}
        return self._cache

    async def _write(self, doc: dict[str, Any]) -> None:
        await self._storage.put(DOCUMENT, json.dumps(doc, sort_keys=True).encode(), "application/json")
        self._cache = doc

    async def seen(self, pass_id: str, day: str, at: str) -> None:
        """Note that a pass was used on `day` (UTC+4), so the admin overview lists it."""
        async with self._lock:
            doc = dict(await self._read())
            passes = dict(doc.get("passes", {}))
            entry = dict(passes.get(pass_id, {"first_seen": at, "days": []}))
            if day in entry["days"]:
                return
            entry["days"] = [*entry["days"], day][-14:]
            passes[pass_id] = entry
            doc["passes"] = passes
            await self._write(doc)

    async def passes_on(self, day: str) -> list[tuple[str, str]]:
        """(pass id, first seen) of the passes used on `day`, oldest first."""
        passes = (await self._read()).get("passes", {})
        found = [(pid, e["first_seen"]) for pid, e in passes.items() if day in e.get("days", [])]
        return sorted(found, key=lambda p: p[1])

    async def reserve_override(self) -> float | None:
        """The judges' daily reserve the admin set, if any; it can only lower the calendar's."""
        value = (await self._read()).get("reserve_usd")
        return None if value is None else float(value)

    async def set_reserve(self, usd: float | None) -> None:
        if usd is not None and usd < 0:
            raise ValueError("the reserve must not be negative")
        async with self._lock:
            doc = dict(await self._read())
            doc["reserve_usd"] = usd
            await self._write(doc)


class JudgePassesToday:
    """For the admin overview: each pass used today, with the stories it started and what it spent."""

    def __init__(
        self,
        desk: JudgeDesk,
        quota: VisitorQuota | None,
        ledger: SpendLedger,
        clock: Clock,
        day: Callable[[datetime], str],
    ) -> None:
        self._desk, self._quota, self._ledger, self._clock, self._day = desk, quota, ledger, clock, day

    async def execute(self) -> list[PassActivity]:
        day = self._day(self._clock.now())
        found = []
        for pass_id, first_seen in await self._desk.passes_on(day):
            stories = await self._quota.used(pass_key(pass_id), day, "projects") if self._quota else 0
            spent = await self._ledger.spent_on_day(pass_pool(day, pass_id))
            found.append(PassActivity(pass_id, first_seen, stories, round(spent, 4)))
        return found
