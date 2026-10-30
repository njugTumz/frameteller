"""Gates (ADR 0016): past a limit, work waits in line with its place and an estimate; judges go first."""

import asyncio

import pytest

from frameteller.application.capacity import Gate, waiting_var
from frameteller.application.lanes import Lane, lane_var


class Recorder:
    def __init__(self) -> None:
        self.places: dict[str, list[int]] = {}

    def report(self, name: str):  # type: ignore[no-untyped-def]
        async def tell(place: int, estimate_s: float) -> None:
            self.places.setdefault(name, []).append(place)

        return tell


async def hold(gate: Gate, release: asyncio.Event, order: list[str], name: str, rec: Recorder | None = None) -> None:
    async with gate.slot(rec.report(name) if rec else None):
        order.append(name)
        await release.wait()


async def test_past_the_limit_work_waits_and_learns_its_place() -> None:
    gate, release, order, rec = Gate("images", 2, typical_s=10), asyncio.Event(), list[str](), Recorder()
    tasks = [asyncio.create_task(hold(gate, release, order, n, rec)) for n in "abcd"]
    await asyncio.sleep(0.01)
    assert order == ["a", "b"]
    state = gate.state()
    assert (state.in_flight, state.waiting) == (2, 2)
    assert rec.places == {"c": [1], "d": [2]}
    assert gate.estimate(1) == 10
    assert gate.estimate(3) == 20
    release.set()
    await asyncio.gather(*tasks)
    assert order == ["a", "b", "c", "d"]
    assert rec.places["c"][-1] == 0
    assert rec.places["d"][-1] == 0
    assert gate.state().served == 4
    assert gate.state().max_waiting == 2


async def test_judges_go_ahead_of_the_public_line() -> None:
    gate, release, order = Gate("images", 1, typical_s=1), asyncio.Event(), list[str]()
    first = asyncio.create_task(hold(gate, release, order, "first"))
    await asyncio.sleep(0)
    public = [asyncio.create_task(hold(gate, release, order, f"public{i}")) for i in range(2)]
    await asyncio.sleep(0)
    token = lane_var.set(Lane.JUDGE)
    judge = asyncio.create_task(hold(gate, release, order, "judge"))
    lane_var.reset(token)
    await asyncio.sleep(0.01)
    release.set()
    await asyncio.gather(first, judge, *public)
    assert order == ["first", "judge", "public0", "public1"]


async def test_leaving_the_line_moves_everyone_up() -> None:
    gate, release, order, rec = Gate("sessions", 1, typical_s=5), asyncio.Event(), list[str](), Recorder()
    first = asyncio.create_task(hold(gate, release, order, "a", rec))
    await asyncio.sleep(0)
    b = asyncio.create_task(hold(gate, release, order, "b", rec))
    c = asyncio.create_task(hold(gate, release, order, "c", rec))
    await asyncio.sleep(0.01)
    b.cancel()
    with pytest.raises(asyncio.CancelledError):
        await b
    await asyncio.sleep(0.01)
    assert rec.places["c"] == [2, 1]
    release.set()
    await asyncio.gather(first, c)
    assert order == ["a", "c"]
    assert gate.state().in_flight == 0


async def test_bypass_takes_a_slot_past_the_limit() -> None:
    gate, release, order = Gate("sessions", 1, typical_s=5), asyncio.Event(), list[str]()
    a = asyncio.create_task(hold(gate, release, order, "a"))
    await asyncio.sleep(0)

    async def judge() -> None:
        async with gate.slot(bypass=True):
            order.append("judge")

    await judge()
    assert order == ["a", "judge"]
    release.set()
    await a


async def test_a_gate_reports_through_the_context_of_the_work() -> None:
    gate, release, order, rec = Gate("images", 1, typical_s=5), asyncio.Event(), list[str](), Recorder()
    a = asyncio.create_task(hold(gate, release, order, "a"))
    await asyncio.sleep(0)

    async def job() -> None:
        waiting_var.set(rec.report("job"))  # what the job runner does
        async with gate.slot():
            pass

    b = asyncio.create_task(job())
    await asyncio.sleep(0.01)
    release.set()
    await asyncio.gather(a, b)
    assert rec.places["job"] == [1, 0]
