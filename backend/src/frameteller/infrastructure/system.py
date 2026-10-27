"""Clock and id adapters backed by the system."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class RandomIds:
    """Random, URL-safe ids. Unguessable, because a project id is all it takes to open a project."""

    def new_id(self) -> str:
        return uuid.uuid4().hex
