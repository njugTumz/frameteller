"""The waiting room (ADR 0016): past the live-session limit, a new session waits in line instead of failing."""

import asyncio
from collections.abc import Callable

from tests.interface.conftest import Api, WsClient
from tests.interface.test_judge import TOKEN

FRAME = b"\x00\x00" * 1920


async def second_project(api: Api, headers: dict[str, str] | None = None) -> str:
    r = await api.client.post("/projects", json={"title": "Second"}, headers=headers or {})
    return str(r.json()["id"])


async def test_a_session_past_the_limit_waits_with_its_place_then_starts(make_api: Callable[..., Api]) -> None:
    api = make_api(capacity_sessions=1)
    other = await second_project(api)
    first = WsClient(api.app, "/ws/projects/p1/session")
    assert await first.connect()
    await first.send_json({"mode": "narrate"})
    assert (await first.receive() or {})["type"] == "session.started"

    second = WsClient(api.app, f"/ws/projects/{other}/session")
    assert await second.connect()
    await second.send_json({"mode": "narrate"})
    waiting = await second.receive()
    assert waiting == {"type": "queue.waiting", "position": 1, "estimate_s": 150.0}
    assert api.container.capacity.sessions.state().waiting == 1

    await first.send_bytes(FRAME)
    await first.send_json({"type": "end"})
    await first.until("session.ended")
    assert (await second.receive() or {})["type"] == "session.started"
    await second.send_json({"type": "end"})
    await second.until("session.ended")
    await first.finish()
    await second.finish()


async def test_leaving_the_waiting_room_frees_the_place(make_api: Callable[..., Api]) -> None:
    api = make_api(capacity_sessions=1)
    other = await second_project(api)
    first = WsClient(api.app, "/ws/projects/p1/session")
    assert await first.connect()
    await first.send_json({"mode": "narrate"})
    await first.receive()
    second = WsClient(api.app, f"/ws/projects/{other}/session")
    assert await second.connect()
    await second.send_json({"mode": "narrate"})
    assert (await second.receive() or {})["type"] == "queue.waiting"
    await second.disconnect()
    await asyncio.wait_for(second.task, 5)
    assert api.container.capacity.sessions.state().waiting == 0
    await first.send_json({"type": "end"})
    await first.until("session.ended")
    await first.finish()


async def test_judges_never_wait(make_api: Callable[..., Api]) -> None:
    api = make_api(capacity_sessions=1, judge_token=TOKEN)
    other = await second_project(api)
    first = WsClient(api.app, "/ws/projects/p1/session")
    assert await first.connect()
    await first.send_json({"mode": "narrate"})
    await first.receive()
    cookie = (await api.client.post("/judge", json={"token": TOKEN})).headers["set-cookie"].split(";")[0]
    judge = WsClient(api.app, f"/ws/projects/{other}/session", headers={"cookie": cookie})
    assert await judge.connect()
    await judge.send_json({"mode": "narrate"})
    assert (await judge.receive() or {})["type"] == "session.started"
    for ws in (first, judge):
        await ws.send_json({"type": "end"})
        await ws.until("session.ended")
        await ws.finish()
