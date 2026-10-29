"""Pure ASGI middleware: request ids and access logs, body size limits, and per-IP rate limits.

Pure ASGI (not BaseHTTPMiddleware) so WebSockets and streamed responses pass through untouched.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from frameteller.infrastructure.observability import log_context
from frameteller.interface.ratelimit import TokenBucketLimiter

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

log = logging.getLogger("frameteller.access")

MAX_BODY_BYTES = 64 * 1024
# Spoken edit instructions: up to 30 s of 24 kHz mono 16-bit WAV.
MAX_AUDIO_BODY_BYTES = 44 + 48 * 30_000
_AUDIO_BODY = re.compile(r"/dictation$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
# Endpoints that spend model credits get a tighter bucket.
_COSTLY = re.compile(r"/(panel|panel/edit|panel/select|panel/layers|animatic|regenerate|merge|session|dictation)$")
_UNLIMITED = {"/healthz", "/readyz"}


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return str(value.decode("latin-1"))
    return None


async def _send_json(send: Send, status: int, body: dict[str, Any], headers: list[tuple[bytes, bytes]]) -> None:
    payload = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                *headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class RequestContextMiddleware:
    """Every log line carries the request id; the response echoes it in X-Request-ID."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        incoming = _header(scope, b"x-request-id")
        request_id = incoming if incoming and _REQUEST_ID.match(incoming) else uuid.uuid4().hex
        status = {"code": 0}
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", [])
                message["headers"] = [*message["headers"], (b"x-request-id", request_id.encode())]
            await send(message)

        with log_context(request_id=request_id):
            try:
                await self.app(scope, receive, send_with_id)
            finally:
                if scope["path"] not in _UNLIMITED:
                    log.info(
                        "request",
                        extra={
                            "method": scope.get("method", "WS"),
                            "path": scope["path"],
                            "status": status["code"],
                            "latency_ms": round((time.perf_counter() - started) * 1000),
                        },
                    )


class BodyLimitMiddleware:
    """Refuse request bodies over MAX_BODY_BYTES (MAX_AUDIO_BODY_BYTES for dictation), chunked or not."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES, audio_bytes: int = MAX_AUDIO_BODY_BYTES) -> None:
        self.app, self.max_bytes, self.audio_bytes = app, max_bytes, audio_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        limit = self.audio_bytes if _AUDIO_BODY.search(scope["path"]) else self.max_bytes
        length = _header(scope, b"content-length")
        if length is not None and (not length.isdigit() or int(length) > limit):
            await self._too_large(send, limit)
            return
        # Buffer up to the limit, so a chunked body cannot grow past it.
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            size += len(message.get("body", b""))
            if size > limit:
                await self._too_large(send, limit)
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                break
        body = b"".join(chunks)
        sent = False

        async def replay() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _too_large(self, send: Send, limit: int) -> None:
        body = {"error": {"code": "too_large", "message": f"Request bodies are limited to {limit} bytes."}}
        await _send_json(send, 413, body, [])


class RateLimitMiddleware:
    """Token buckets per client IP: one for everything, a tighter one for endpoints that spend credits.

    The client IP is the ASGI client address; behind a proxy, run uvicorn with --proxy-headers and
    --forwarded-allow-ips set to the proxy so it is the real client, not the proxy.
    """

    def __init__(self, app: ASGIApp, *, per_minute: int, costly_per_minute: int) -> None:
        self.app = app
        self.general = TokenBucketLimiter(per_minute)
        self.costly = TokenBucketLimiter(costly_per_minute)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or scope["path"] in _UNLIMITED:
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        wait = self.general.acquire(ip)
        costly = scope["type"] == "websocket" or (scope.get("method") == "POST" and _COSTLY.search(scope["path"]))
        if not wait and costly:
            wait = self.costly.acquire(ip)
        if not wait:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await receive()  # websocket.connect
            await send({"type": "websocket.close", "code": 1008, "reason": "rate limited"})
            return
        body = {"error": {"code": "rate_limited", "message": "Too many requests. Wait a moment and try again."}}
        await _send_json(send, 429, body, [(b"retry-after", str(math.ceil(wait)).encode())])


PAUSED_MESSAGE = "Frameteller is taking a short break. Back soon."
# Still served while paused: probes, the status the studio checks, and shared storyboards.
_OPEN_WHILE_PAUSED = re.compile(r"^/(healthz|readyz|status|s/[^/]+|shares/.+)$")


class PauseMiddleware:
    """DEMO_PAUSED: the kill switch. Every endpoint but the open ones answers 503 "back soon"; sessions close."""

    def __init__(self, app: ASGIApp, *, paused: bool) -> None:
        self.app, self.paused = app, paused

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.paused or scope["type"] not in ("http", "websocket") or _OPEN_WHILE_PAUSED.match(scope["path"]):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await receive()  # websocket.connect
            await send({"type": "websocket.close", "code": 4503, "reason": "paused"})
            return
        if scope.get("method") == "OPTIONS":  # let CORS preflights through, so the browser sees the 503 body
            await self.app(scope, receive, send)
            return
        await _send_json(
            send, 503, {"error": {"code": "paused", "message": PAUSED_MESSAGE}}, [(b"retry-after", b"600")]
        )
