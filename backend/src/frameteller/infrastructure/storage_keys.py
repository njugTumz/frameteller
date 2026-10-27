"""Storage keys are ours, but they include ids from URLs: check them before they reach a disk or a blob name."""

from __future__ import annotations

import re

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.:-]*$")


def check_key(key: str) -> str:
    """Return the key if it is a plain relative path; refuse absolute paths, traversal and odd characters."""
    if not _SAFE_KEY.match(key) or ".." in key.split("/") or len(key) > 1024:
        raise ValueError(f"unsafe storage key {key!r}")
    return key
