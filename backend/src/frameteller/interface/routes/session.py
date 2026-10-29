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

from frameteller.application.errors import ApplicationError, ProjectNotFoundError, ScriptError
from frameteller.application.events import ProjectEvent
from frameteller.application.scripts import accept_script
from frameteller.application.use_cases import ClientInput, ReadControl, ReadingOptions
from frameteller.application.use_cases.voices import DEFAULT_VOICE
from frameteller.domain import DomainError, Script, ScriptFormat
from frameteller.infrastructure.observability import log_context
from frameteller.interface.dto import (
    ClientBeat,
    ClientContinue,
    ClientCorrection,
    ClientEnd,
    ClientMessage,
    ClientPause,
    SessionStart,
    error_message,
    event_message,
)
from frameteller.interface.errors import describe
from frameteller.interface.routes.deps import PROJECT_ID, Deps
from frameteller.interface.routes.voices import NOT_SET_UP
from frameteller.interface.visitor import visitor_id

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
    """Validated client input until it sends {"type": "end"}, disconnects or hits 55 minutes.

    PCM frames, beats (timed at the end of the audio received so far) and transcript corrections, in order.
    """

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.received_ms = 0
        self.disconnected = False
        self.notices: list[str] = []

    async def frames(self) -> AsyncIterator[ClientInput]:
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
            elif (parsed := await self._parse(message.get("text"))) is not None:
                if isinstance(parsed, ClientEnd):
                    return
                yield parsed.at(self.received_ms) if isinstance(parsed, ClientBeat) else parsed.as_command()

    async def controls(self) -> AsyncIterator[ReadControl]:
        """ "Read it to me": Pause and Continue until the client ends or leaves. Audio is not expected."""
        while True:
            try:
                message = await self.ws.receive()
            except WebSocketDisconnect:
                self.disconnected = True
                return
            if message["type"] == "websocket.disconnect":
                self.disconnected = True
                return
            parsed = _parse(message.get("text"))
            if isinstance(parsed, ClientEnd):
                return
            if isinstance(parsed, ClientPause | ClientContinue):
                yield parsed.type
            else:
                await self._notice('While a voice reads, send {"type": "pause"}, {"type": "continue"} or end.')

    async def _parse(self, text: str | None) -> ClientEnd | ClientBeat | ClientCorrection | None:
        parsed = _parse(text)
        if isinstance(parsed, ClientPause | ClientContinue):
            parsed = None  # only while a voice reads
        if parsed is None:
            await self._notice('Unknown message: send {"type": "beat"}, {"type": "transcript.corrected", ...} or end.')
        return parsed

    async def _notice(self, text: str) -> None:
        if text not in self.notices:  # say it once, not once per frame
            self.notices.append(text)
            await _send(self.ws, error_message(text))


def _parse(text: str | None) -> ClientEnd | ClientBeat | ClientCorrection | ClientPause | ClientContinue | None:
    try:
        return ClientMessage.model_validate({"message": json.loads(text or "")}).message
    except (ValueError, ValidationError):
        return None


async def _send(ws: WebSocket, message: dict[str, Any]) -> bool:
    try:
        await ws.send_json(message)
        return True
    except Exception:  # disconnected, closed or broken: stop sending, never crash the session
        return False


async def _forward(ws: WebSocket, events: asyncio.Queue[ProjectEvent]) -> None:
    while await _send(ws, event_message(await events.get())):
        pass


async def _close(ws: WebSocket, code: int) -> None:
    """Close, unless the client already left (uvicorn then raises ClientDisconnected, an OSError)."""
    with contextlib.suppress(Exception):
        await ws.close(code)


async def _refuse(ws: WebSocket, code: int, message: str) -> None:
    await ws.accept()
    await _send(ws, error_message(message, fatal=True))
    await _close(ws, code)


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
        await _send(
            ws,
            error_message(
                'Start with {"mode": "narrate" | "co_direct" | "teleprompter" | "read", "keywords": [...]}.', fatal=True
            ),
        )
        await _close(ws, CLOSE_BAD_REQUEST)
        return
    except WebSocketDisconnect:
        return
    script: Script | None = None
    reading: ReadingOptions | None = None
    try:
        if start.scripted:
            script = accept_script(start.script or "", ScriptFormat(start.script_format), c.settings.demo_limits)
        if start.mode == "read":
            if c.read_script is None or c.list_voices is None:
                raise ScriptError(NOT_SET_UP)
            voice = start.voice or DEFAULT_VOICE
            language = await c.list_voices.check(voice, start.language or "en")
            reading = ReadingOptions(voice, language.locale, visitor_id(ws))
    except ApplicationError as e:
        await _send(ws, error_message(e.user_message, fatal=True))
        await _close(ws, CLOSE_BAD_REQUEST)
        return

    audio = Audio(ws)
    with c.hub.subscribe(project_id) as events:
        forward = asyncio.create_task(_forward(ws, events))
        try:
            await _send(ws, {"type": "session.started", "mode": start.mode})
            try:
                if reading is not None and script is not None and c.read_script is not None:
                    await c.read_script.execute(project_id, script, reading, audio.controls())
                else:
                    await c.voice_session.execute(
                        project_id, audio.frames(), start.as_options(), keep_audio=start.keep_audio, script=script
                    )
            except ApplicationError as e:
                await _send(ws, error_message(e.user_message, fatal=True))
            except Exception:
                log.exception("voice session failed")
                await _send(ws, error_message(ApplicationError.user_message, fatal=True))
            c.sessions.release(project_id)  # a new narration may start; this socket keeps reporting jobs
            if not audio.disconnected:
                await _drain_until_closed(ws, project_id, c)
        finally:
            await asyncio.sleep(0)  # let the forwarder flush events already queued
            forward.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await forward
    await _close(ws, 1000)


async def _drain_until_closed(ws: WebSocket, project_id: str, c: Deps) -> None:
    """After the narration: keep the socket for job updates and transcript corrections until the client leaves."""
    with contextlib.suppress(TimeoutError, WebSocketDisconnect):
        async with asyncio.timeout(IDLE_AFTER_SESSION_S):
            while (message := await ws.receive())["type"] != "websocket.disconnect":
                if isinstance(parsed := _parse(message.get("text")), ClientCorrection):
                    try:
                        await c.correct_transcript.execute(project_id, parsed.turn_id, parsed.text)
                    except (ApplicationError, DomainError) as e:
                        await _send(ws, error_message(describe(e)[2]))
