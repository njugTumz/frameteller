"""MetaVoiceTranscribeAdapter: realtime and file speech-to-text (CLAUDE.md section 5).

Realtime protocol: auth in the first JSON frame (the HTTP Authorization header is ignored), sent within 10 s;
wait for the {sessionId} acknowledgement; stream raw PCM s16le mono at real time; end with {"type":"endStream"}
and read until close code 1000. Sessions last at most 60 minutes and cannot be resumed.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time
import urllib.request
import uuid
import wave
from collections.abc import AsyncIterator
from typing import Any

import websockets
import websockets.exceptions

from frameteller.application.errors import ModelRejectedError, ModelUnavailableError
from frameteller.application.ports import (
    AudioProgress,
    PartialTranscript,
    SpeakerIdentified,
    SpeechEvent,
    SpeechMode,
    SpeechOptions,
    TurnCompleted,
    TurnEnded,
    TurnStarted,
)
from frameteller.domain import TranscriptTurn
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.pricing import asr_cost
from frameteller.infrastructure.resilience import ModelCaller, RetryPolicy, Usage, classify

log = logging.getLogger("frameteller.models")

SAMPLE_RATE = 24_000
BYTES_PER_MS = SAMPLE_RATE * 2 // 1000  # PCM_24KHZ s16le mono = 48 bytes/ms
FRAME_MS = 80
MAX_SESSION_MS = 60 * 60 * 1000
HANDSHAKE_TIMEOUT_S = 10
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_FILE_MS = 10 * 60 * 1000

_MODES = {SpeechMode.NARRATION: "ENDPOINTING", SpeechMode.CO_DIRECTION: "DIARIZATION"}


async def paced_pcm(pcm: bytes, frame_ms: int = FRAME_MS) -> AsyncIterator[bytes]:
    """Yield PCM in frames at real time. The server rejects streams that run ahead; a live mic is paced already."""
    step = frame_ms * BYTES_PER_MS
    started = time.perf_counter()
    for i, offset in enumerate(range(0, len(pcm), step)):
        await asyncio.sleep(max(0.0, started + i * frame_ms / 1000 - time.perf_counter()))
        yield pcm[offset : offset + step]


class MetaVoiceTranscribeAdapter:
    """SpeechToTextPort."""

    def __init__(self, caller: ModelCaller, settings: Settings) -> None:
        self._caller, self._settings = caller, settings
        self._policy = RetryPolicy(attempts=settings.retry_attempts, timeout_s=settings.text_timeout_s * 5)

    def _handshake(self, options: SpeechOptions) -> dict[str, Any]:
        frame: dict[str, Any] = {
            "model": self._settings.asr_model,
            "authorization": {"accessToken": f"Bearer {self._settings.model_api_key.get_secret_value()}"},
            "audioEncoding": "PCM_24KHZ",
            "mode": _MODES[options.mode],
            "partialMode": "CUMULATIVE",
        }
        # Keywords and language bias are fixed for the session.
        if options.keywords:
            frame["keywords"] = list(options.keywords)
        if options.language_bias:
            frame["languageBias"] = options.language_bias
        return frame

    async def stream(self, audio: AsyncIterator[bytes], options: SpeechOptions) -> AsyncIterator[SpeechEvent]:
        model = self._settings.asr_model
        breaker = self._caller.breaker(model)
        breaker.before_call()
        started = time.perf_counter()
        sent_bytes = 0
        ok = False
        try:
            async with websockets.connect(
                self._settings.meta_realtime_url, open_timeout=HANDSHAKE_TIMEOUT_S, max_size=None
            ) as ws:
                await asyncio.wait_for(ws.send(json.dumps(self._handshake(options))), HANDSHAKE_TIMEOUT_S)
                await asyncio.wait_for(_await_session(ws), HANDSHAKE_TIMEOUT_S)

                async def send() -> None:
                    nonlocal sent_bytes
                    async for chunk in audio:
                        if (sent_bytes + len(chunk)) // BYTES_PER_MS > MAX_SESSION_MS:
                            break  # 60-minute session limit: close the input cleanly
                        await ws.send(chunk)
                        sent_bytes += len(chunk)
                    await ws.send(json.dumps({"type": "endStream"}))

                sender = asyncio.create_task(send())
                try:
                    async for event in _events(ws):
                        yield event
                finally:
                    if not sender.done():
                        sender.cancel()
                    await asyncio.gather(sender, return_exceptions=True)
                if not sender.cancelled() and (send_error := sender.exception()) is not None:
                    raise send_error
                if ws.close_code != 1000:
                    raise ModelUnavailableError(model, f"stream closed with code {ws.close_code}")
            ok = True
            breaker.success()
        except Exception as exc:
            # The cause (close code and reason, HTTP status) is what tells a pacing problem from an outage.
            log.warning(
                "voice stream failed",
                extra={
                    "model": model,
                    "error": type(exc).__name__,
                    "detail": str(exc)[:300],
                    "sent_ms": sent_bytes // BYTES_PER_MS,
                },
            )
            mapped = classify(model, exc)
            if mapped is None:
                raise
            error, retryable = mapped
            if retryable:
                breaker.failure()
            raise error from exc
        finally:
            audio_ms = sent_bytes // BYTES_PER_MS
            latency = round((time.perf_counter() - started) * 1000)
            # Audio the server received is billed whether or not the session ended cleanly.
            await self._caller.record(model, "stream", latency, Usage(asr_cost(audio_ms)), ok=ok)

    async def transcribe_file(self, wav: bytes, options: SpeechOptions) -> list[TranscriptTurn]:
        """Fallback: POST /v1/asr/transcribe with a WAV (mono, 16-bit, 16 or 24 kHz, <= 32 MB and 10 minutes)."""
        audio_ms = _check_wav(self._settings.asr_model, wav)
        # The file endpoint needs audioEncoding "WAV" (400 "You must specify the 'audioEncoding' field" without it,
        # "Malformed request" with PCM_24KHZ); auth goes in the HTTP header instead of the request.
        drop = ("authorization", "partialMode")
        request = {k: v for k, v in self._handshake(options).items() if k not in drop} | {"audioEncoding": "WAV"}
        body, content_type = _multipart(request, wav)
        url = self._settings.meta_base_url.rstrip("/") + "/asr/transcribe"
        key = self._settings.model_api_key.get_secret_value()

        def post() -> dict[str, Any]:
            req = urllib.request.Request(
                url, data=body, method="POST", headers={"Authorization": f"Bearer {key}", "Content-Type": content_type}
            )
            with urllib.request.urlopen(req, timeout=self._policy.timeout_s) as r:
                result: dict[str, Any] = json.loads(r.read())
                return result

        async def call() -> tuple[dict[str, Any], Usage]:
            return await asyncio.to_thread(post), Usage(asr_cost(audio_ms))

        data = await self._caller.call(self._settings.asr_model, "transcribe_file", call, self._policy)
        return [
            TranscriptTurn(str(t["turnId"]), t["transcript"], int(t["startMs"]), int(t["endMs"]), t.get("speaker"))
            for t in data.get("turns", [])
        ]


async def _await_session(ws: Any) -> str:
    async for raw in ws:
        if isinstance(raw, str):
            message = json.loads(raw)
            if "sessionId" in message:
                return str(message["sessionId"])
    raise ModelUnavailableError("muse-voice-transcribe-1.0", "closed before the session started")


async def _events(ws: Any) -> AsyncIterator[SpeechEvent]:
    """Translate server events to typed events. Turn state is keyed on turnId because turns can overlap.

    Measured on a real session (Day 2 findings): turnId is an integer; `speaker` events carry `label` and no
    turnId, and arrive while their turn is still open; `audioProgress` arrives every 80 ms.
    """
    starts: dict[str, int] = {}
    ends: dict[str, int] = {}
    speakers: dict[str, str] = {}
    current: str | None = None  # the most recent turn that started and has not completed
    try:
        async for raw in ws:
            if not isinstance(raw, str):
                continue
            ev = json.loads(raw)
            kind = ev.get("type")
            tid = str(ev["turnId"]) if ev.get("turnId") is not None else None
            if kind == "speechStart" and tid is not None:
                starts[tid] = int(ev.get("audioProcessedMs", 0))
                current = tid
                yield TurnStarted(tid, starts[tid])
            elif kind == "transcript":
                if ev.get("final") and not ev.get("transcript"):
                    continue  # end-of-stream marker; the final text came with speechComplete
                # CUMULATIVE partials replace the previous one; they belong to the most recent speechStart.
                yield PartialTranscript(str(ev.get("transcript", "")).strip())
            elif kind == "speechEnd" and tid is not None:
                ends[tid] = int(ev.get("audioProcessedMs", 0))
                yield TurnEnded(tid, ends[tid])
            elif kind == "speaker":
                target = tid or current
                label = ev.get("label") or ev.get("speaker")
                if target is not None and label:
                    speakers[target] = str(label)
                    yield SpeakerIdentified(target, speakers[target])
            elif kind == "speechComplete" and tid is not None:
                start = starts.pop(tid, 0)
                end = max(ends.pop(tid, start), start)
                if current == tid:
                    current = None
                text = str(ev.get("transcript", "")).strip()
                yield TurnCompleted(TranscriptTurn(tid, text, start, end, speakers.pop(tid, None)))
            elif kind == "audioProgress" and ev.get("audioProcessedMs") is not None:
                yield AudioProgress(int(ev["audioProcessedMs"]))
            # Unknown event types are ignored on purpose.
    except websockets.exceptions.ConnectionClosedOK:
        return


def _check_wav(model: str, wav: bytes) -> int:
    if len(wav) > MAX_FILE_BYTES:
        raise ModelRejectedError(model, "audio file is larger than 32 MB")
    try:
        with wave.open(io.BytesIO(wav)) as w:
            channels, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    except (wave.Error, EOFError) as e:
        raise ModelRejectedError(model, "audio is not a WAV file") from e
    if channels != 1 or width != 2 or rate not in (16_000, 24_000):
        raise ModelRejectedError(model, "audio must be mono, 16-bit PCM at 16 or 24 kHz")
    audio_ms = int(frames) * 1000 // int(rate)
    if audio_ms > MAX_FILE_MS:
        raise ModelRejectedError(model, "audio is longer than 10 minutes")
    return audio_ms


def _multipart(request: dict[str, Any], wav: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="request"\r\n'
        f"Content-Type: application/json\r\n\r\n{json.dumps(request)}\r\n"
        f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="audio.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode()
    return head + wav + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"
