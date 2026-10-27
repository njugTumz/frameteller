from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from frameteller.application.errors import ApplicationError
from frameteller.application.events import SessionEnded, SessionFailed, ShotCreated, TranscriptUpdated, TurnFinished
from frameteller.application.ports import (
    EventPublisher,
    PartialTranscript,
    SpeechOptions,
    SpeechToTextPort,
    TurnCompleted,
)
from frameteller.application.use_cases.direct_turn import DirectTurn
from frameteller.application.use_cases.requests import RequestCastReferences
from frameteller.domain import DomainError, TranscriptTurn

DIRECTION_FAILED = "The director couldn't place that line. Try saying it again."


class RunVoiceSession:
    """Live narration: transcribe, direct each finished turn into shots, and queue sheets for new characters.

    The transcript is never held up by direction: turns are directed one at a time, in order, beside the stream
    (ADR 0002). A failed turn is reported and skipped; the session carries on.
    """

    def __init__(
        self,
        speech: SpeechToTextPort,
        direct: DirectTurn,
        cast: RequestCastReferences,
        events: EventPublisher,
    ) -> None:
        self._speech, self._direct, self._cast, self._events = speech, direct, cast, events

    async def execute(self, project_id: str, audio: AsyncIterator[bytes], options: SpeechOptions) -> SessionEnded:
        turns: asyncio.Queue[TranscriptTurn | None] = asyncio.Queue()
        counts = {"turns": 0, "shots": 0}

        async def publish_failure(message: str, *, fatal: bool = False) -> None:
            await self._events.publish(project_id, SessionFailed(message, fatal))

        async def direct_turns() -> None:
            while (turn := await turns.get()) is not None:
                try:
                    directed = await self._direct.execute(project_id, turn)
                    for shot in directed.shots:
                        counts["shots"] += 1
                        await self._events.publish(project_id, ShotCreated(shot))
                    if directed.new_characters:
                        await self._cast.execute(project_id, [c.id for c in directed.new_characters])
                except ApplicationError as e:
                    await publish_failure(e.user_message)
                except DomainError:
                    await publish_failure(DIRECTION_FAILED)

        director = asyncio.create_task(direct_turns())
        try:
            async for event in self._speech.stream(audio, options):
                if isinstance(event, PartialTranscript):
                    await self._events.publish(project_id, TranscriptUpdated(event.text))
                elif isinstance(event, TurnCompleted):
                    counts["turns"] += 1
                    await self._events.publish(project_id, TurnFinished(event.turn))
                    if event.turn.text.strip():
                        turns.put_nowait(event.turn)
        except ApplicationError as e:
            await publish_failure(e.user_message, fatal=True)
        except BaseException:
            director.cancel()
            raise
        turns.put_nowait(None)
        await director  # finish directing what was said before the stream ended
        ended = SessionEnded(counts["turns"], counts["shots"])
        await self._events.publish(project_id, ended)
        return ended
