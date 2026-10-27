"""In-process fan-out of project events to live WebSocket connections, and the one-session-per-project rule."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

from frameteller.application.events import ProjectEvent

log = logging.getLogger("frameteller.events")

QUEUE_SIZE = 1000


class EventHub:
    """EventPublisher. Each subscriber gets its own bounded queue; a stalled client never blocks a job."""

    def __init__(self) -> None:
        self._subscribers: defaultdict[str, set[asyncio.Queue[ProjectEvent]]] = defaultdict(set)

    async def publish(self, project_id: str, event: ProjectEvent) -> None:
        for queue in list(self._subscribers.get(project_id, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("dropped event for a slow subscriber", extra={"event": type(event).__name__})

    @contextmanager
    def subscribe(self, project_id: str) -> Iterator[asyncio.Queue[ProjectEvent]]:
        queue: asyncio.Queue[ProjectEvent] = asyncio.Queue(QUEUE_SIZE)
        self._subscribers[project_id].add(queue)
        try:
            yield queue
        finally:
            self._subscribers[project_id].discard(queue)
            if not self._subscribers[project_id]:
                del self._subscribers[project_id]


class ActiveSessions:
    """At most one live voice session per project: two would interleave turns into one shot list."""

    def __init__(self) -> None:
        self._active: set[str] = set()

    def claim(self, project_id: str) -> bool:
        if project_id in self._active:
            return False
        self._active.add(project_id)
        return True

    def release(self, project_id: str) -> None:
        self._active.discard(project_id)
