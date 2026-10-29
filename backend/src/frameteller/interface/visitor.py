"""Who a visitor is, for the per-visitor demo limits: a hash of the client IP and a random browser id.

The studio keeps the browser id in localStorage and sends it as X-Visitor-Id. Neither the IP nor the browser id
is stored: only the hash, in the daily quota counters.
"""

from __future__ import annotations

import hashlib
import re

from starlette.requests import HTTPConnection

VISITOR_HEADER = "X-Visitor-Id"
_BROWSER_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def visitor_id(connection: HTTPConnection) -> str:
    ip = connection.client.host if connection.client else "unknown"
    browser = connection.headers.get(VISITOR_HEADER, "")
    browser = browser if _BROWSER_ID.match(browser) else ""
    return hashlib.sha256(f"{ip}|{browser}".encode()).hexdigest()[:32]
