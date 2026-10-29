"""Timeouts, bounded retries with jittered backoff, a circuit breaker per model, error mapping and usage records.

Retries happen here only (SDK retries are disabled), and only for rate limits, 5xx, timeouts and dropped
connections. Everything else fails fast as a ModelRejectedError, and unknown exceptions propagate unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import urllib.error
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

import httpx2
import openai
import websockets.exceptions

from frameteller.application.errors import (
    InvalidModelOutputError,
    ModelError,
    ModelRateLimitedError,
    ModelRejectedError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from frameteller.application.ports import SpendLedger, UsageRecord
from frameteller.infrastructure.observability import project_id_var

T = TypeVar("T")
log = logging.getLogger("frameteller.models")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    timeout_s: float = 60.0
    base_delay_s: float = 0.5
    max_delay_s: float = 8.0
    # A 429 means "later", not "broken": it gets more tries, waits longer, and never opens the breaker, so a
    # busy minute queues work instead of failing it (ADR 0016).
    rate_limited_attempts: int = 6
    rate_limited_max_delay_s: float = 20.0

    def delay(self, attempt: int, rand: Callable[[], float] = random.random) -> float:
        """Full jitter: uniform in [0, min(max, base * 2**attempt)]."""
        cap: float = min(self.max_delay_s, self.base_delay_s * 2**attempt)
        return rand() * cap

    def rate_limited_delay(self, attempt: int, retry_after_s: float | None, rand: Callable[[], float]) -> float:
        """The server's Retry-After when it gives one (capped), else jittered backoff from at least 1 s."""
        if retry_after_s is not None:
            return min(self.rate_limited_max_delay_s, max(0.0, retry_after_s)) + rand()
        cap: float = min(self.rate_limited_max_delay_s, max(1.0, self.base_delay_s * 2 ** (attempt + 1)))
        return cap / 2 + rand() * cap / 2


def retry_after(exc: BaseException) -> float | None:
    """Seconds from a Retry-After header on a provider's 429, when there is one."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    value = headers.get("retry-after") if headers is not None else None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class CircuitBreaker:
    """Opens after `failures` consecutive provider failures; lets one trial call through after `cooldown_s`."""

    model: str
    failures: int = 5
    cooldown_s: float = 30.0
    clock: Callable[[], float] = time.monotonic
    _consecutive: int = 0
    _opened_at: float | None = None

    def before_call(self) -> None:
        if self._opened_at is None:
            return
        if self.clock() - self._opened_at < self.cooldown_s:
            raise ModelUnavailableError(self.model, "circuit open")
        self._opened_at = None  # half-open: allow a trial call

    def success(self) -> None:
        self._consecutive, self._opened_at = 0, None

    def failure(self) -> None:
        self._consecutive += 1
        if self._consecutive >= self.failures:
            self._opened_at = self.clock()
            log.warning("circuit opened", extra={"model": self.model, "consecutive_failures": self._consecutive})

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None


@dataclass(slots=True)
class Breakers:
    failures: int = 5
    cooldown_s: float = 30.0
    clock: Callable[[], float] = time.monotonic
    _by_model: dict[str, CircuitBreaker] = field(default_factory=dict)

    def for_model(self, model: str) -> CircuitBreaker:
        if model not in self._by_model:
            self._by_model[model] = CircuitBreaker(model, self.failures, self.cooldown_s, self.clock)
        return self._by_model[model]


def classify(model: str, exc: BaseException) -> tuple[ModelError, bool] | None:
    """Map a provider failure to (application error, retryable). None means: not a provider failure."""
    if isinstance(exc, ModelError):
        return exc, False
    if isinstance(exc, TimeoutError | openai.APITimeoutError):
        return ModelTimeoutError(model, "timed out"), True
    if isinstance(exc, openai.RateLimitError):
        return ModelRateLimitedError(model, "rate limited"), True
    if isinstance(exc, openai.APIStatusError):
        return _by_status(model, exc.status_code)
    if isinstance(exc, openai.APIConnectionError):
        return ModelUnavailableError(model, "connection failed"), True
    if isinstance(exc, urllib.error.HTTPError):
        return _by_status(model, exc.code)
    if isinstance(exc, httpx2.HTTPStatusError):
        return _by_status(model, exc.response.status_code)
    if isinstance(exc, httpx2.TimeoutException):
        return ModelTimeoutError(model, "timed out"), True
    if isinstance(exc, httpx2.TransportError):
        return ModelUnavailableError(model, type(exc).__name__), True
    if isinstance(exc, urllib.error.URLError | ConnectionError | websockets.exceptions.ConnectionClosedError):
        return ModelUnavailableError(model, type(exc).__name__), True
    if isinstance(exc, websockets.exceptions.InvalidStatus):
        return _by_status(model, exc.response.status_code)
    return None


def _by_status(model: str, status: int) -> tuple[ModelError, bool]:
    if status == 429:
        return ModelRateLimitedError(model, "HTTP 429"), True
    if status >= 500:
        return ModelUnavailableError(model, f"HTTP {status}"), True
    return ModelRejectedError(model, f"HTTP {status}"), False


@dataclass(frozen=True, slots=True)
class Usage:
    """What an adapter reports about a successful call."""

    cost_usd: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None


class ModelCaller:
    """Runs one model operation with timeout, retries, circuit breaker and a usage record per attempt."""

    def __init__(
        self,
        ledger: SpendLedger,
        breakers: Breakers,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        self._ledger, self._breakers, self._sleep, self._rand = ledger, breakers, sleep, rand

    async def call(
        self,
        model: str,
        operation: str,
        fn: Callable[[], Awaitable[tuple[T, Usage]]],
        policy: RetryPolicy,
    ) -> T:
        breaker = self._breakers.for_model(model)
        attempts = max(policy.attempts, policy.rate_limited_attempts)
        failures = 0  # attempts that failed for a reason other than a rate limit
        for attempt in range(attempts):
            breaker.before_call()
            started = time.perf_counter()
            try:
                result, usage = await asyncio.wait_for(fn(), policy.timeout_s)
            except InvalidModelOutputError:
                breaker.success()  # the provider worked; the answer was unusable
                raise
            except Exception as exc:
                mapped = classify(model, exc)
                await self.record(model, operation, _since(started), Usage(0.0), ok=False)
                if mapped is None:
                    raise
                error, retryable = mapped
                limited = isinstance(error, ModelRateLimitedError)
                if retryable and not limited:
                    breaker.failure()
                    failures += 1
                log.warning(
                    "model call failed",
                    extra={"model": model, "operation": operation, "attempt": attempt + 1, "error": str(error)},
                )
                out_of_tries = attempt + 1 == attempts if limited else failures >= policy.attempts
                if not retryable or out_of_tries or breaker.is_open:
                    raise error from exc
                if limited:
                    await self._sleep(policy.rate_limited_delay(attempt, retry_after(exc), self._rand))
                else:
                    await self._sleep(policy.delay(attempt, self._rand))
                continue
            breaker.success()
            await self.record(model, operation, _since(started), usage, ok=True)
            return result
        raise AssertionError("unreachable")  # pragma: no cover

    def breaker(self, model: str) -> CircuitBreaker:
        return self._breakers.for_model(model)

    async def record(self, model: str, operation: str, latency_ms: int, usage: Usage, *, ok: bool) -> None:
        """For calls that cannot go through call(), such as a live audio stream."""
        record = UsageRecord(
            model=model,
            operation=operation,
            latency_ms=latency_ms,
            cost_usd=usage.cost_usd,
            project_id=project_id_var.get(),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_tokens=usage.cached_tokens,
            ok=ok,
        )
        await self._ledger.record_usage(record)
        log.info(
            "model call",
            extra={
                "model": model,
                "operation": operation,
                "latency_ms": latency_ms,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cached_tokens": usage.cached_tokens,
                "cost_usd": round(usage.cost_usd, 6),
                "ok": ok,
            },
        )


def _since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
