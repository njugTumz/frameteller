"""Glimmer only while it is warm: user traffic never wakes the GPU (ADR 0013, amended).

Any request to the Modal endpoint, even /health, starts a container, so there is no free way to ask whether
Glimmer is up. Instead the warm-up script (deploy/modal/warm.py --keep) holds a lease: it wakes Glimmer, checks
it answers, then renews a short lease here every few minutes while it keeps the GPU busy. While the lease holds,
reviews use the screen (Glimmer, Spark confirms its flags). Without one, or once Glimmer fails a review, Spark
reviews alone. A forgotten or crashed warm-up script therefore costs at most one lease, never a wake.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta

import httpx2
from openai import AsyncOpenAI

from frameteller.application.ports import Clock, MediaStoragePort, ReviewerPort, ReviewRequest
from frameteller.domain import MediaRef, Verdict

log = logging.getLogger("frameteller.models")

LEASE_KEY = "system/glimmer-lease.json"  # not under projects/, so /media never serves it
MAX_LEASE_MINUTES = 30
REFRESH_S = 15  # how long a read of the stored lease is trusted


class GlimmerLease:
    """When Glimmer is known to be warm. Kept in storage so it survives a restart of the replica."""

    def __init__(self, storage: MediaStoragePort, clock: Clock) -> None:
        self._storage, self._clock = storage, clock
        self._until: datetime | None = None
        self._read_at: datetime | None = None

    async def warm_until(self) -> datetime | None:
        now = self._clock.now()
        if self._read_at is None or now - self._read_at > timedelta(seconds=REFRESH_S):
            self._until, self._read_at = await self._load(), now
        return self._until if self._until and self._until > now else None

    async def grant(self, minutes: int) -> datetime:
        until = self._clock.now() + timedelta(minutes=max(1, min(minutes, MAX_LEASE_MINUTES)))
        await self._store(until)
        return until

    async def hold_until(self, until: datetime) -> datetime:
        """Warm until `until` (at most MAX_LEASE_MINUTES ahead): the judges' keeper renews it (ADR 0020)."""
        latest = self._clock.now() + timedelta(minutes=MAX_LEASE_MINUTES)
        until = min(until, latest)
        await self._store(until)
        return until

    async def revoke(self) -> None:
        await self._store(None)

    async def lost(self, reason: str) -> None:
        """Glimmer timed out or failed although the lease held: no more reviews go to it until it is renewed."""
        log.warning("glimmer lease revoked", extra={"reason": reason[:200]})
        await self.revoke()

    async def _store(self, until: datetime | None) -> None:
        body = {"warm_until": until.isoformat() if until else None}
        await self._storage.put(LEASE_KEY, json.dumps(body).encode(), "application/json")
        self._until, self._read_at = until, self._clock.now()

    async def _load(self) -> datetime | None:
        try:
            raw = json.loads(await self._storage.get(MediaRef(LEASE_KEY)))
            return datetime.fromisoformat(raw["warm_until"]) if raw.get("warm_until") else None
        except Exception:  # missing or unreadable: not warm, which is the safe answer
            return None


class WarmGatedReviewer:
    """The Glimmer reviewer (screen or fallback) while the lease holds, Spark otherwise."""

    def __init__(self, warm: ReviewerPort, cold: ReviewerPort, lease: GlimmerLease) -> None:
        self._warm, self._cold, self._lease = warm, cold, lease

    async def review(self, request: ReviewRequest) -> Verdict:
        if await self._lease.warm_until() is None:
            return await self._cold.review(request)
        return await self._warm.review(request)


class ModalGlimmerWarmer:
    """GlimmerWarmerPort over our Modal endpoint, as deploy/modal/warm.py does it: poll /health (no token) until
    vLLM is up, then one tiny authenticated chat request to prove it answers."""

    def __init__(self, http: httpx2.AsyncClient, client: AsyncOpenAI, base_url: str, model: str) -> None:
        self._http, self._client, self._model = http, client, model
        self._health = base_url.strip().rstrip("/").removesuffix("/v1") + "/health"

    async def wake(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                r = await self._http.get(self._health, timeout=60)
                if r.status_code == 200:
                    break
            except httpx2.HTTPError:
                pass  # starting: the request times out or the proxy answers 5xx
            if time.monotonic() > deadline:
                raise TimeoutError(f"glimmer not up after {timeout_s:.0f} s")
            await asyncio.sleep(10)
        await self.ping()

    async def ping(self) -> None:
        await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": "Reply with the single word: ready"}],
            max_tokens=512,
            extra_body={"chat_template_kwargs": {"reasoning_strength": "low"}},
            timeout=120,
        )
