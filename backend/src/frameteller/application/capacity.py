"""Capacity and fairness (ADR 0016): global limits on live sessions, model calls in flight and exports.

Past a limit, work waits in line instead of failing. Each gate keeps its line in arrival order, with judges
ahead of the public, and tells every waiter its place and an estimate whenever the line moves. The estimate is
the place in line times a moving average of how long a slot is held, divided by the slots.

One replica (ADR 0009), so the gates are in memory.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from frameteller.application.lanes import is_judge
from frameteller.application.ports import (
    EditRequest,
    ImageGenerationPort,
    ImageRequest,
    Segment,
    SegmentationPort,
    StoredImage,
)
from frameteller.domain import MediaRef, Point

log = logging.getLogger("frameteller.capacity")

# (place in line, estimated seconds): place 1 is next; place 0 means the wait is over.
WaitReport = Callable[[int, float], Awaitable[None]]
# Set by whoever can tell the user (the job runner, a session): a gate deep in a use case reports through it.
waiting_var: ContextVar[WaitReport | None] = ContextVar("waiting", default=None)

EWMA = 0.2  # weight of the newest hold time in the moving average


@dataclass(slots=True)
class _Waiter:
    future: asyncio.Future[None]
    judge: bool
    report: WaitReport | None
    since: float
    told: int = -1  # the place last reported


@dataclass(frozen=True, slots=True)
class GateState:
    name: str
    limit: int
    in_flight: int
    waiting: int
    hold_s: float  # moving average of how long a slot is held
    longest_wait_s: float  # the oldest waiter's wait so far
    served: int
    waited: int  # how many had to wait at all
    max_waiting: int  # the longest line seen


class Gate:
    def __init__(self, name: str, limit: int, typical_s: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        if limit < 1:
            raise ValueError("a gate needs at least one slot")
        self.name, self.limit, self._clock = name, limit, clock
        self._hold_s = typical_s
        self._in_flight = 0
        self._line: list[_Waiter] = []
        self._served = self._waited = self._max_waiting = 0
        self._reports: set[asyncio.Task[None]] = set()

    def estimate(self, place: int) -> float:
        """Seconds until a waiter at `place` gets a slot: whole rounds of the slots ahead of it."""
        return round(math.ceil(place / self.limit) * self._hold_s, 1)

    @asynccontextmanager
    async def slot(self, report: WaitReport | None = None, *, bypass: bool = False) -> AsyncIterator[None]:
        """Hold one slot. `bypass` takes one even past the limit (a judge's live session)."""
        report = report or waiting_var.get()
        if bypass or (self._in_flight < self.limit and not self._line):
            self._in_flight += 1
        else:
            await self._wait(report)
        started = self._clock()
        try:
            yield
        finally:
            held = self._clock() - started
            self._hold_s = (1 - EWMA) * self._hold_s + EWMA * held
            self._served += 1
            self._release()

    async def _wait(self, report: WaitReport | None) -> None:
        waiter = _Waiter(asyncio.get_running_loop().create_future(), is_judge(), report, self._clock())
        at = len(self._line)
        if waiter.judge:  # ahead of every public waiter, behind the judges already waiting
            at = next((i for i, w in enumerate(self._line) if not w.judge), len(self._line))
        self._line.insert(at, waiter)
        self._waited += 1
        self._max_waiting = max(self._max_waiting, len(self._line))
        self._tell()
        try:
            await waiter.future
        except asyncio.CancelledError:
            if waiter.future.done() and not waiter.future.cancelled():
                self._release()  # granted just as it was cancelled: give the slot back
            else:
                with contextlib.suppress(ValueError):
                    self._line.remove(waiter)
                self._tell()
            raise
        if waiter.told > 0 and waiter.report is not None:
            self._send(waiter.report, 0, 0.0)

    def _release(self) -> None:
        self._in_flight -= 1
        while self._line and self._in_flight < self.limit:
            waiter = self._line.pop(0)
            self._in_flight += 1
            waiter.future.set_result(None)
        self._tell()

    def _tell(self) -> None:
        for place, waiter in enumerate(self._line, start=1):
            if waiter.report is not None and waiter.told != place:
                waiter.told = place
                self._send(waiter.report, place, self.estimate(place))

    def _send(self, report: WaitReport, place: int, estimate: float) -> None:
        async def run() -> None:
            try:
                await report(place, estimate)
            except Exception:
                log.exception("wait report failed", extra={"gate": self.name})

        task = asyncio.ensure_future(run())
        self._reports.add(task)
        task.add_done_callback(self._reports.discard)

    def state(self) -> GateState:
        now = self._clock()
        oldest = max((now - w.since for w in self._line), default=0.0)
        return GateState(
            self.name,
            self.limit,
            self._in_flight,
            len(self._line),
            round(self._hold_s, 2),
            round(oldest, 1),
            self._served,
            self._waited,
            self._max_waiting,
        )


@dataclass(frozen=True, slots=True)
class CapacityLimits:
    sessions: int = 24
    images: int = 8
    sam: int = 4
    exports: int = 2


@dataclass(slots=True)
class Capacity:
    """The studio's gates. Typical hold times seed the estimates until real ones are measured."""

    limits: CapacityLimits = field(default_factory=CapacityLimits)
    sessions: Gate = field(init=False)
    images: Gate = field(init=False)
    sam: Gate = field(init=False)
    exports: Gate = field(init=False)

    def __post_init__(self) -> None:
        self.sessions = Gate("sessions", self.limits.sessions, typical_s=150)
        self.images = Gate("images", self.limits.images, typical_s=25)
        self.sam = Gate("sam", self.limits.sam, typical_s=5)
        self.exports = Gate("exports", self.limits.exports, typical_s=40)

    def states(self) -> list[GateState]:
        return [g.state() for g in (self.sessions, self.images, self.sam, self.exports)]


class GatedImages:
    """ImageGenerationPort through the images gate: at most `limit` Muse Image calls in flight."""

    def __init__(self, images: ImageGenerationPort, gate: Gate) -> None:
        self._images, self._gate = images, gate

    async def generate(self, request: ImageRequest, store_as: str) -> StoredImage:
        async with self._gate.slot():
            return await self._images.generate(request, store_as)

    async def edit(self, request: EditRequest, store_as: str) -> StoredImage:
        async with self._gate.slot():
            return await self._images.edit(request, store_as)


class GatedSegmentation:
    """SegmentationPort through the SAM gate."""

    def __init__(self, segmentation: SegmentationPort, gate: Gate) -> None:
        self._sam, self._gate = segmentation, gate

    async def segment_concept(self, image: MediaRef, concept: str, store_prefix: str) -> list[Segment]:
        async with self._gate.slot():
            return await self._sam.segment_concept(image, concept, store_prefix)

    async def segment_point(self, image: MediaRef, point: Point, store_prefix: str) -> Segment | None:
        async with self._gate.slot():
            return await self._sam.segment_point(image, point, store_prefix)
