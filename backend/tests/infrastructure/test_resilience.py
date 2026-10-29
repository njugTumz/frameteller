import urllib.error
from collections.abc import Awaitable, Callable

import httpx2
import openai
import pytest

from frameteller.application.errors import (
    InvalidModelOutputError,
    ModelRateLimitedError,
    ModelRejectedError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from frameteller.infrastructure.observability import log_context
from frameteller.infrastructure.pricing import asr_cost, token_cost
from frameteller.infrastructure.resilience import Breakers, ModelCaller, RetryPolicy, Usage, classify
from tests.fakes import InMemorySpendLedger

REQ = httpx2.Request("POST", "https://api.meta.ai/v1/responses")


def status_error(code: int, headers: dict[str, str] | None = None) -> openai.APIStatusError:
    response = httpx2.Response(code, request=REQ, headers=headers)
    cls = openai.RateLimitError if code == 429 else openai.APIStatusError
    return cls(f"HTTP {code}", response=response, body=None)


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class Harness:
    def __init__(self) -> None:
        self.ledger = InMemorySpendLedger()
        self.clock = Clock()
        self.breakers = Breakers(failures=3, cooldown_s=30, clock=self.clock)
        self.sleeps: list[float] = []

        async def sleep(s: float) -> None:
            self.sleeps.append(s)

        self.caller = ModelCaller(self.ledger, self.breakers, sleep=sleep, rand=lambda: 1.0)

    def flaky(self, *errors: BaseException) -> Callable[[], Awaitable[tuple[str, Usage]]]:
        queue = list(errors)

        async def fn() -> tuple[str, Usage]:
            if queue:
                raise queue.pop(0)
            return "ok", Usage(0.01, 10, 20, 5)

        return fn


POLICY = RetryPolicy(attempts=3, timeout_s=5, base_delay_s=0.5, max_delay_s=8)


async def test_retries_rate_limits_and_5xx_with_backoff_then_succeeds() -> None:
    h = Harness()
    result = await h.caller.call("muse-image-1.0", "generate", h.flaky(status_error(429), status_error(503)), POLICY)
    assert result == "ok"
    assert h.sleeps == [1.0, 1.0]  # a 429 waits at least 1 s
    assert [u.ok for u in h.ledger.usage] == [False, False, True]


async def test_rate_limits_queue_longer_and_never_open_the_breaker() -> None:
    h = Harness()  # the breaker opens after 3 failures, and the policy allows 3 attempts for other errors
    result = await h.caller.call("muse-image-1.0", "generate", h.flaky(*[status_error(429)] * 5), POLICY)
    assert result == "ok"
    assert len(h.sleeps) == 5
    assert not h.breakers.for_model("muse-image-1.0").is_open
    assert max(h.sleeps) <= POLICY.rate_limited_max_delay_s + 1


async def test_rate_limits_give_up_after_their_own_bound() -> None:
    h = Harness()
    with pytest.raises(ModelRateLimitedError):
        await h.caller.call("muse-image-1.0", "generate", h.flaky(*[status_error(429)] * 9), POLICY)
    assert len(h.sleeps) == POLICY.rate_limited_attempts - 1


async def test_rate_limits_honour_retry_after() -> None:
    h = Harness()
    await h.caller.call("muse-image-1.0", "generate", h.flaky(status_error(429, {"retry-after": "7"})), POLICY)
    assert h.sleeps == [8.0]  # 7 s and up to 1 s of jitter


async def test_does_not_retry_client_errors() -> None:
    h = Harness()
    with pytest.raises(ModelRejectedError) as e:
        await h.caller.call("muse-image-1.0", "generate", h.flaky(status_error(400)), POLICY)
    assert h.sleeps == []
    assert "couldn't do that" in e.value.user_message


async def test_gives_up_after_bounded_attempts() -> None:
    h = Harness()
    errors = [status_error(500)] * 5
    with pytest.raises(ModelUnavailableError):
        await h.caller.call("muse-image-1.0", "generate", h.flaky(*errors), POLICY)
    assert len(h.sleeps) == 2


async def test_timeout_is_mapped_and_retried() -> None:
    import asyncio

    h = Harness()
    calls = 0

    async def slow() -> tuple[str, Usage]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)
        return "late", Usage(0)

    with pytest.raises(ModelTimeoutError):
        await h.caller.call("sam-3.1", "segment", slow, RetryPolicy(attempts=2, timeout_s=0.01))
    assert calls == 2


async def test_circuit_opens_per_model_and_recovers_after_cooldown() -> None:
    h = Harness()
    one_try = RetryPolicy(attempts=1)
    for _ in range(3):
        with pytest.raises(ModelUnavailableError):
            await h.caller.call("sam-3.1", "segment", h.flaky(status_error(502)), one_try)
    with pytest.raises(ModelUnavailableError, match="circuit open"):
        await h.caller.call("sam-3.1", "segment", h.flaky(), one_try)
    # other models are unaffected
    assert await h.caller.call("muse-image-1.0", "generate", h.flaky(), one_try) == "ok"
    h.clock.t = 31
    assert await h.caller.call("sam-3.1", "segment", h.flaky(), one_try) == "ok"


async def test_open_circuit_stops_retrying_early() -> None:
    h = Harness()
    with pytest.raises(ModelUnavailableError):
        await h.caller.call("sam-3.1", "segment", h.flaky(*[status_error(500)] * 5), RetryPolicy(attempts=6))
    assert len(h.sleeps) == 2  # third failure opened the circuit


async def test_invalid_output_is_not_a_provider_failure() -> None:
    h = Harness()
    with pytest.raises(InvalidModelOutputError):
        await h.caller.call("muse-spark-1.3", "direct", h.flaky(InvalidModelOutputError("muse-spark-1.3")), POLICY)
    assert not h.breakers.for_model("muse-spark-1.3").is_open
    assert h.sleeps == []


async def test_unknown_exceptions_propagate_unchanged() -> None:
    h = Harness()
    with pytest.raises(KeyError):
        await h.caller.call("muse-image-1.0", "generate", h.flaky(KeyError("bug")), POLICY)


async def test_usage_is_recorded_with_tokens_cost_and_project() -> None:
    h = Harness()
    with log_context(project_id="p1"):
        await h.caller.call("muse-spark-1.3", "direct_turn", h.flaky(), POLICY)
    u = h.ledger.usage[0]
    assert (u.model, u.operation, u.project_id, u.ok) == ("muse-spark-1.3", "direct_turn", "p1", True)
    assert (u.input_tokens, u.output_tokens, u.cached_tokens, u.cost_usd) == (10, 20, 5, 0.01)
    assert u.latency_ms >= 0


@pytest.mark.parametrize(
    ("exc", "kind", "retryable"),
    [
        (urllib.error.HTTPError("u", 429, "x", {}, None), ModelRateLimitedError, True),  # type: ignore[arg-type]
        (urllib.error.HTTPError("u", 404, "x", {}, None), ModelRejectedError, False),  # type: ignore[arg-type]
        (urllib.error.URLError("dns"), ModelUnavailableError, True),
        (ConnectionResetError(), ModelUnavailableError, True),
        (openai.APIConnectionError(request=REQ), ModelUnavailableError, True),
        (openai.APITimeoutError(request=REQ), ModelTimeoutError, True),
    ],
)
def test_classify(exc: BaseException, kind: type, retryable: bool) -> None:
    mapped = classify("m", exc)
    assert mapped is not None
    assert isinstance(mapped[0], kind)
    assert mapped[1] is retryable


def test_prices() -> None:
    assert token_cost("muse-spark-1.3-contributor", 1_000_000, 1_000_000, 0) == pytest.approx(0.30)
    assert token_cost("muse-spark-1.3", 1_000_000, 0, 1_000_000) == pytest.approx(0.15)
    assert token_cost("unknown", 10, 10, 0) == 0
    assert asr_cost(1) == pytest.approx(0.18 / 3600)  # whole seconds
    assert asr_cost(3_600_000) == pytest.approx(0.18)
