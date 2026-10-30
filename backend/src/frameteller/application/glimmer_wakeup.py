"""Judges wake Muse Glimmer (ADR 0020): a request with a judge pass starts the GPU in the background.

Until Glimmer answers, Muse Spark reviews as before. Once it answers, a keeper holds the lease that puts reviews in
screen mode (Glimmer screens, Spark confirms its flags), renewing it to 5 minutes after the last judge activity and
pinging Glimmer so Modal keeps the container up. When judges go quiet the lease runs out, and Modal scales to zero
5 minutes later. Public visitors never call this, so they never wake the GPU.

Two caps per day (UTC+4): 10 wake-ups, and USD 5 of estimated Modal time for them. Past either, judges get Spark.
The estimate is GPU time from the wake-up request until Modal scales down, at the configured hourly price.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from frameteller.application.ports import Clock, GlimmerLeasePort, GlimmerWarmerPort, MediaStoragePort
from frameteller.domain import MediaRef

log = logging.getLogger("frameteller.glimmer")

DOCUMENT = "admin/glimmer-wakes.json"  # under admin/, never served by /media
DAYS_KEPT = 14


@dataclass(frozen=True, slots=True)
class WakePolicy:
    wakes_per_day: int = 10
    usd_per_day: float = 5.0
    usd_per_hour: float = 3.95  # Modal H100, per second of GPU time
    idle_minutes: float = 5  # the lease ends this long after the last judge activity
    scaledown_minutes: float = 5  # Modal keeps an idle container this long (deploy/modal/glimmer.py)
    ping_every_s: float = 240  # under Modal's scale-down window
    tick_s: float = 30  # how often the keeper renews the lease
    wake_timeout_s: float = 900


@dataclass(frozen=True, slots=True)
class GlimmerToday:
    """For the admin overview."""

    day: str
    wakes: int
    wakes_cap: int
    estimated_usd: float
    usd_cap: float
    warm_until: datetime | None
    waking: bool
    last_cold_start_s: float | None


class JudgeGlimmer:
    """Wakes Glimmer for judges and keeps it leased while they are active. One replica (ADR 0009)."""

    def __init__(
        self,
        lease: GlimmerLeasePort,
        warmer: GlimmerWarmerPort,
        storage: MediaStoragePort,
        clock: Clock,
        day: Callable[[datetime], str],
        policy: WakePolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._lease, self._warmer, self._storage, self._clock, self._day = lease, warmer, storage, clock, day
        self._policy, self._sleep = policy or WakePolicy(), sleep
        self._lock = asyncio.Lock()
        self._last: datetime | None = None
        self._task: asyncio.Task[None] | None = None
        self._started: datetime | None = None  # of the wake-up in progress or being kept

    async def judge_active(self) -> bool:
        """A judge did something. True if this started a wake-up."""
        now = self._clock.now()
        self._last = now
        async with self._lock:
            if self._task is not None and not self._task.done():
                return False  # waking or kept: the keeper sees the new activity
            if await self._lease.warm_until() is not None:
                return False  # already warm (e.g. the warm-up script holds it)
            day = self._day(now)
            today = await self._today(day)
            if today["wakes"] >= self._policy.wakes_per_day or today["usd"] >= self._policy.usd_per_day:
                log.info("judge glimmer wake-up skipped: today's cap is reached", extra={"day": day, **today})
                return False
            today["wakes"] += 1
            await self._save(day, today)
            self._started = now
            self._task = asyncio.create_task(self._run(now, day))
            log.info("judge glimmer wake-up started", extra={"day": day, "wakes": today["wakes"]})
            return True

    async def today(self) -> GlimmerToday:
        now = self._clock.now()
        day = self._day(now)
        today = await self._today(day)
        running = self._task is not None and not self._task.done()
        usd = today["usd"] + (self._cost(self._started, now) if running and self._started else 0.0)
        return GlimmerToday(
            day=day,
            wakes=today["wakes"],
            wakes_cap=self._policy.wakes_per_day,
            estimated_usd=round(usd, 4),
            usd_cap=self._policy.usd_per_day,
            warm_until=await self._lease.warm_until(),
            waking=running and await self._lease.warm_until() is None,
            last_cold_start_s=today.get("last_cold_start_s"),
        )

    async def wait(self) -> None:
        """For tests and shutdown: until the current wake-up and keeper are done."""
        if self._task is not None:
            await self._task

    async def _run(self, started: datetime, day: str) -> None:
        p = self._policy
        try:
            try:
                await self._warmer.wake(p.wake_timeout_s)
            except Exception as e:
                log.warning("judge glimmer wake-up failed; reviews stay with Spark", extra={"reason": str(e)[:200]})
                return
            cold = (self._clock.now() - started).total_seconds()
            await self._update(day, last_cold_start_s=round(cold, 1))
            log.info("glimmer is warm for judges", extra={"cold_start_s": round(cold, 1)})
            pinged = self._clock.now()
            while True:
                now = self._clock.now()
                until = (self._last or started) + timedelta(minutes=p.idle_minutes)
                if now >= until:
                    break  # judges went quiet: the lease runs out at `until`
                spent = (await self._today(day))["usd"] + self._cost(started, now)
                if spent >= p.usd_per_day:
                    log.warning("judge glimmer spend guard reached; back to Spark", extra={"usd": round(spent, 2)})
                    await self._lease.revoke()
                    break
                await self._lease.hold_until(until)
                if (now - pinged).total_seconds() >= p.ping_every_s:
                    try:
                        await self._warmer.ping()
                    except Exception as e:
                        log.warning("glimmer stopped answering; back to Spark", extra={"reason": str(e)[:200]})
                        await self._lease.revoke()
                        break
                    pinged = now
                await self._sleep(min(p.tick_s, max(1.0, (until - now).total_seconds())))
        finally:
            ended = self._clock.now()
            today = await self._today(day)
            await self._update(day, usd=round(today["usd"] + self._cost(started, ended), 4))
            self._started = None

    def _cost(self, started: datetime | None, until: datetime) -> float:
        """Estimated Modal cost of one wake-up: GPU time until `until`, plus the idle minutes before scale-down."""
        if started is None:
            return 0.0
        seconds = max(0.0, (until - started).total_seconds()) + 60 * self._policy.scaledown_minutes
        return seconds * self._policy.usd_per_hour / 3600

    async def _today(self, day: str) -> dict[str, Any]:
        days = (await self._read()).get("days", {})
        entry = dict(days.get(day, {}))
        return {"wakes": int(entry.get("wakes", 0)), "usd": float(entry.get("usd", 0.0)), **_extra(entry)}

    async def _update(self, day: str, **fields: Any) -> None:
        today = await self._today(day)
        today.update(fields)
        await self._save(day, today)

    async def _save(self, day: str, entry: dict[str, Any]) -> None:
        doc = await self._read()
        days = dict(doc.get("days", {}))
        days[day] = entry
        kept = dict(sorted(days.items())[-DAYS_KEPT:])
        await self._storage.put(DOCUMENT, json.dumps({"days": kept}, sort_keys=True).encode(), "application/json")

    async def _read(self) -> dict[str, Any]:
        try:
            ref = MediaRef(DOCUMENT)
            if not await self._storage.exists(ref):
                return {}
            doc = json.loads(await self._storage.get(ref))
            return doc if isinstance(doc, dict) else {}
        except Exception:  # unreadable: start the day afresh rather than block judges
            return {}


def _extra(entry: dict[str, Any]) -> dict[str, Any]:
    cold = entry.get("last_cold_start_s")
    return {"last_cold_start_s": float(cold)} if isinstance(cold, int | float) and not math.isnan(cold) else {}
