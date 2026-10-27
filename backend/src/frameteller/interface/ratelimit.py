"""A small in-process token-bucket rate limiter per client IP (one container; no external store)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class TokenBucketLimiter:
    """`per_minute` requests per key on average, with bursts up to `burst`."""

    MAX_KEYS = 10_000

    def __init__(self, per_minute: int, burst: int | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._rate = per_minute / 60.0
        self._burst = float(burst or per_minute)
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def acquire(self, key: str) -> float:
        """Take one token. Returns 0 if allowed, else the seconds until a token is free."""
        now = self._clock()
        bucket = self._buckets.get(key)
        if bucket is None:
            if len(self._buckets) >= self.MAX_KEYS:
                self._prune(now)
            bucket = self._buckets[key] = _Bucket(self._burst, now)
        bucket.tokens = min(self._burst, bucket.tokens + (now - bucket.updated) * self._rate)
        bucket.updated = now
        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return 0.0
        return (1 - bucket.tokens) / self._rate

    def _prune(self, now: float) -> None:
        """Forget buckets that have refilled completely: they behave exactly like new ones."""
        full = [k for k, b in self._buckets.items() if b.tokens + (now - b.updated) * self._rate >= self._burst]
        for k in full:
            del self._buckets[k]
