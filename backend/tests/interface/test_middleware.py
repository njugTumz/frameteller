from collections.abc import AsyncIterator, Callable

from frameteller.interface.ratelimit import TokenBucketLimiter
from tests.interface.conftest import Api


async def test_request_id_is_echoed_or_generated(api: Api) -> None:
    r = await api.client.get("/healthz", headers={"X-Request-ID": "demo-request-0001"})
    assert r.headers["x-request-id"] == "demo-request-0001"
    r = await api.client.get("/healthz", headers={"X-Request-ID": "bad id!"})
    assert len(r.headers["x-request-id"]) == 32


async def test_bodies_over_64_kb_are_refused(api: Api) -> None:
    r = await api.client.post("/projects", content=b'{"title": "' + b"x" * 70_000 + b'"}')
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "too_large"

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(70):
            yield b"x" * 1024

    r = await api.client.post("/projects", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


async def test_rate_limit_per_client_with_retry_after(make_api: Callable[..., Api]) -> None:
    api = make_api(rate_limit_per_minute=3)
    codes = [(await api.client.get("/projects/p1")).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = await api.client.get("/projects/p1")
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert (await api.client.get("/healthz")).status_code == 200  # probes are never limited


async def test_costly_endpoints_have_their_own_bucket(make_api: Callable[..., Api]) -> None:
    api = make_api(rate_limit_costly_per_minute=1)
    assert (await api.client.post("/projects/p1/shots/1/panel", json={})).status_code == 202
    assert (await api.client.post("/projects/p1/shots/2/panel", json={})).status_code == 429
    assert (await api.client.get("/projects/p1")).status_code == 200


async def test_cors_allows_only_configured_origins(make_api: Callable[..., Api]) -> None:
    api = make_api(allowed_origins="https://app.example, https://staging.example/")
    preflight = {"Access-Control-Request-Method": "POST"}
    ok = await api.client.options("/projects", headers={"Origin": "https://staging.example", **preflight})
    assert ok.headers["access-control-allow-origin"] == "https://staging.example"
    bad = await api.client.options("/projects", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in bad.headers


def test_token_bucket_refills_over_time() -> None:
    now = [0.0]
    limiter = TokenBucketLimiter(60, burst=2, clock=lambda: now[0])
    assert [limiter.acquire("ip") for _ in range(2)] == [0.0, 0.0]
    assert limiter.acquire("ip") == 1.0  # one token per second
    now[0] = 1.0
    assert limiter.acquire("ip") == 0.0
    assert limiter.acquire("other") == 0.0


def test_token_bucket_prunes_idle_clients() -> None:
    now = [0.0]
    limiter = TokenBucketLimiter(60, clock=lambda: now[0])
    limiter.MAX_KEYS = 2
    limiter.acquire("a")
    limiter.acquire("b")
    now[0] = 120.0  # both refilled
    limiter.acquire("c")
    assert set(limiter._buckets) == {"c"}
