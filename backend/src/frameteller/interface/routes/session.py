"""WebSocket /ws/projects/{id}/session: live narration in, typed project events out (docs/api-events.md)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from frameteller.application.errors import ApplicationError, ProjectNotFoundError
from frameteller.application.events import ProjectEvent
from frameteller.infrastructure.observability import log_context
from frameteller.interface.dto import SessionStart, error_message, event_message
from frameteller.interface.routes.deps import PROJECT_ID, Deps

router = APIRouter()
log = logging.getLogger("frameteller.session")

BYTES_PER_MS = 48  # PCM s16le mono 24 kHz
MAX_FRAME_BYTES = 32 * 1024  # about 0.34 s of audio; browsers send 10-100 ms frames
MAX_SESSION_MS = 55 * 60 * 1000  # below the service's 60-minute limit, so we end the stream cleanly
START_TIMEOUT_S = 10
IDLE_AFTER_SESSION_S = 15 * 60  # keep pushing job updates this long after the narration ends

# Close codes in the 4000 range are ours (RFC 6455 private use).
CLOSE_BAD_REQUEST, CLOSE_NOT_FOUND, CLOSE_BUSY = 4400, 4404, 4409


class Audio:
    """Validated PCM frames from the client until it sends {"type": "end"}, disconnects or hits 55 minutes."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.received_ms = 0
        self.disconnected = False
        self.notices: list[str] = []

    async def frames(self) -> AsyncIterator[bytes]:
        while True:
            try:
                message = await self.ws.receive()
            except WebSocketDisconnect:
                self.disconnected = True
                return
            if message["type"] == "websocket.disconnect":
                self.disconnected = True
                return
            data: bytes | None = message.get("bytes")
            if data is not None:
                if not data or len(data) % 2 or len(data) > MAX_FRAME_BYTES:
                    await self._notice(
                        f"Dropped an audio frame: send 16-bit PCM frames of at most {MAX_FRAME_BYTES} bytes."
                    )
                    continue
                if self.received_ms + len(data) // BYTES_PER_MS > MAX_SESSION_MS:
                    await self._notice(
                        "Sessions are limited to 55 minutes, so this one has ended. Start a new one to go on."
                    )
                    return
                self.received_ms += len(data) // BYTES_PER_MS
                yield data
            elif _is_end(message.get("text")):
                return

    async def _notice(self, text: str) -> None:
        if text not in self.notices:  # say it once, not once per frame
            self.notices.append(text)
            await _send(self.ws, error_message(text))


def _is_end(text: str | None) -> bool:
    try:
        return bool(text) and json.loads(text or "").get("type") == "end"
    except (ValueError, AttributeError):
        return False


async def _send(ws: WebSocket, message: dict[str, Any]) -> bool:
    try:
        await ws.send_json(message)
        return True
    except Exception:  # disconnected, closed or broken: stop sending, never crash the session
        return False


async def _forward(ws: WebSocket, events: asyncio.Queue[ProjectEvent]) -> None:
    while await _send(ws, event_message(await events.get())):
        pass


async def _refuse(ws: WebSocket, code: int, message: str) -> None:
    await ws.accept()
    await _send(ws, error_message(message, fatal=True))
    await ws.close(code)


def _origin_allowed(ws: WebSocket, allowed: list[str]) -> bool:
    """Browsers always send Origin; other clients (the smoke script) may not. CORS does not cover WebSockets."""
    origin = ws.headers.get("origin")
    return not allowed or origin is None or origin.rstrip("/") in allowed


@router.websocket("/ws/projects/{project_id}/session")
async def voice_session(ws: WebSocket, project_id: str, c: Deps) -> None:
    if not re.match(PROJECT_ID, project_id) or not _origin_allowed(ws, c.settings.origins):
        await ws.close(1008)
        return
    with log_context(project_id=project_id):
        try:
            await c.get_project.execute(project_id)
        except ProjectNotFoundError as e:
            await _refuse(ws, CLOSE_NOT_FOUND, e.user_message)
            return
        if not c.sessions.claim(project_id):
            await _refuse(ws, CLOSE_BUSY, "A voice session is already running for this project.")
            return
        try:
            await _run(ws, project_id, c)
        finally:
            c.sessions.release(project_id)


async def _run(ws: WebSocket, project_id: str, c: Deps) -> None:
    await ws.accept()
    try:
        start = SessionStart.model_validate(await asyncio.wait_for(ws.receive_json(), START_TIMEOUT_S))
    except (TimeoutError, ValidationError, ValueError, KeyError):
        await _send(ws, error_message('Start with {"mode": "narrate" | "co_direct", "keywords": [...]}.', fatal=True))
        await ws.close(CLOSE_BAD_REQUEST)
        return
    except WebSocketDisconnect:
        return

    audio = Audio(ws)
    with c.hub.subscribe(project_id) as events:
        forward = asyncio.create_task(_forward(ws, events))
        try:
            await _send(ws, {"type": "session.started", "mode": start.mode})
            try:
                await c.voice_session.execute(project_id, audio.frames(), start.as_options())
            except ApplicationError as e:
                await _send(ws, error_message(e.user_message, fatal=True))
            except Exception:
                log.exception("voice session failed")
                await _send(ws, error_message(ApplicationError.user_message, fatal=True))
            c.sessions.release(project_id)  # a new narration may start; this socket keeps reporting jobs
            if not audio.disconnected:
                await _drain_until_closed(ws)
        finally:
            await asyncio.sleep(0)  # let the forwarder flush events already queued
            forward.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await forward
    with contextlib.suppress(RuntimeError):
        await ws.close(1000)


async def _drain_until_closed(ws: WebSocket) -> None:
    """After the narration: keep the socket for job.updated / cast.proposed until the client leaves."""
    with contextlib.suppress(TimeoutError, WebSocketDisconnect):
        async with asyncio.timeout(IDLE_AFTER_SESSION_S):
            while (await ws.receive())["type"] != "websocket.disconnect":
                pass
