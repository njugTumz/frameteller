"""The judge pass: a private link sets a signed cookie, and requests carrying it run in the judge lane.

The link is https://app.frameteller.com/judge#<JUDGE_TOKEN>. The token is in the fragment, so it never reaches a
server log; the studio posts it once to POST /judge, which answers with the cookie. The token is never used up:
every browser that posts it gets its own pass. The cookie holds a random pass id and an expiry, with an HMAC of
both keyed from the token: changing JUDGE_TOKEN (rotation) invalidates every pass at once. Version 1 cookies
(issued before passes had ids) stay valid until they run out, each counted as a pass of its own.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from http.cookies import CookieError, SimpleCookie

from frameteller.application.judge import pass_var
from frameteller.application.lanes import Lane, lane_var
from frameteller.interface.middleware import ASGIApp, Receive, Scope, Send

COOKIE = "ft_judge"
VERSION = "v2"


def _key(token: str) -> bytes:
    return hashlib.sha256(f"frameteller-judge-cookie|{token}".encode()).digest()


def _signature(token: str, signed: str) -> str:
    return hmac.new(_key(token), signed.encode(), hashlib.sha256).hexdigest()


def issue(token: str, days: int, now: Callable[[], float] = time.time) -> tuple[str, int]:
    """A new pass: a cookie value valid for `days` with its own random id, and its expiry (Unix seconds)."""
    expires = int(now()) + days * 86_400
    signed = f"{VERSION}.{secrets.token_hex(8)}.{expires}"
    return f"{signed}.{_signature(token, signed)}", expires


def pass_id(token: str | None, value: str | None, now: Callable[[], float] = time.time) -> str | None:
    """The pass id of a valid, unexpired cookie; None for anything else."""
    if not token or not value:
        return None
    parts = value.split(".")
    if len(parts) == 4 and parts[0] == VERSION and parts[1].isalnum() and parts[2].isdigit():
        found, expires, signed = parts[1], int(parts[2]), ".".join(parts[:3])
    elif len(parts) == 3 and parts[0] == "v1" and parts[1].isdigit():
        found, expires, signed = f"v1{parts[2][:14]}", int(parts[1]), ".".join(parts[:2])
    else:
        return None
    ok = expires > now() and hmac.compare_digest(parts[-1], _signature(token, signed))
    return found if ok else None


def valid(token: str | None, value: str | None, now: Callable[[], float] = time.time) -> bool:
    return pass_id(token, value, now) is not None


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
        found = pass_id(self._token(), cookie_value(scope)) if scope["type"] in ("http", "websocket") else None
        if found is None:
            await self.app(scope, receive, send)
            return
        reset, reset_pass = lane_var.set(Lane.JUDGE), pass_var.set(found)
        try:
            await self.app(scope, receive, send)
        finally:
            pass_var.reset(reset_pass)
            lane_var.reset(reset)
