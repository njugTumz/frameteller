"""The judge pass: a private link sets a signed cookie, and requests carrying it run in the judge lane.

The link is https://app.frameteller.com/judge#<JUDGE_TOKEN>. The token is in the fragment, so it never reaches a
server log; the studio posts it once to POST /judge, which answers with the cookie. The cookie holds only an
expiry and an HMAC of it, keyed from the token: changing JUDGE_TOKEN (rotation) invalidates every pass at once.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable
from http.cookies import CookieError, SimpleCookie

from frameteller.application.lanes import Lane, lane_var
from frameteller.interface.middleware import ASGIApp, Receive, Scope, Send

COOKIE = "ft_judge"
VERSION = "v1"


def _key(token: str) -> bytes:
    return hashlib.sha256(f"frameteller-judge-cookie|{token}".encode()).digest()


def _signature(token: str, expires: int) -> str:
    return hmac.new(_key(token), f"{VERSION}.{expires}".encode(), hashlib.sha256).hexdigest()


def issue(token: str, days: int, now: Callable[[], float] = time.time) -> tuple[str, int]:
    """A cookie value valid for `days`, and its expiry (Unix seconds)."""
    expires = int(now()) + days * 86_400
    return f"{VERSION}.{expires}.{_signature(token, expires)}", expires


def valid(token: str | None, value: str | None, now: Callable[[], float] = time.time) -> bool:
    if not token or not value:
        return False
    parts = value.split(".")
    if len(parts) != 3 or parts[0] != VERSION or not parts[1].isdigit():
        return False
    expires = int(parts[1])
    return expires > now() and hmac.compare_digest(parts[2], _signature(token, expires))


def token_matches(token: str | None, offered: str) -> bool:
    return bool(token) and hmac.compare_digest(offered.encode(), (token or "").encode())


def cookie_value(scope: Scope) -> str | None:
    for key, raw in scope.get("headers", []):
        if key == b"cookie":
            try:
                jar = SimpleCookie(raw.decode("latin-1"))
            except CookieError:
                return None
            morsel = jar.get(COOKIE)
            return morsel.value if morsel else None
    return None


class JudgeMiddleware:
    """Puts requests and sessions with a valid judge cookie in the judge lane; everything else is public."""

    def __init__(self, app: ASGIApp, *, token: Callable[[], str | None]) -> None:
        self.app, self._token = app, token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not valid(self._token(), cookie_value(scope)):
            await self.app(scope, receive, send)
            return
        reset = lane_var.set(Lane.JUDGE)
        try:
            await self.app(scope, receive, send)
        finally:
            lane_var.reset(reset)
