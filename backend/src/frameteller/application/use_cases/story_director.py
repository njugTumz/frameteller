"""Direct finished turns in order beside a live session: narration, the teleprompter or "Read it to me"."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from frameteller.application.errors import ApplicationError
from frameteller.application.events import SessionFailed, ShotCreated, ShotUpdated
from frameteller.application.limits import DemoLimits
from frameteller.application.ports import EventPublisher
from frameteller.application.use_cases.correct_transcript import CorrectTranscript
from frameteller.application.use_cases.direct_turn import DirectTurn
from frameteller.application.use_cases.requests import RequestCastReferences
from frameteller.domain import DomainError, TranscriptTurn

DIRECTION_FAILED = "The director couldn't place that line. Try saying it again."
CORRECTION_FAILED = "We couldn't apply that correction. Check the turn and try again."


@dataclass(frozen=True, slots=True)
class TranscriptCorrection:
    """The user fixed misheard words in a turn."""

    turn_id: str
    text: str


class StoryDirector:
    """One turn at a time, in order (ADR 0002): shots, reveals, refusals, the shot limit and sheets for new
    characters. A failure is reported and skipped, and the session carries on."""

    def __init__(
        self,
        direct: DirectTurn,
        correct: CorrectTranscript,
        cast: RequestCastReferences,
        events: EventPublisher,
        limits: DemoLimits | None = None,
    ) -> None:
        self._direct, self._correct, self._cast, self._events, self._limits = direct, correct, cast, events, limits

    async def run(self, project_id: str, work: asyncio.Queue[TranscriptTurn | TranscriptCorrection | None]) -> int:
        """Direct until a None arrives. Returns the number of shots made."""
        shots, told_full = 0, False
        while (item := await work.get()) is not None:
            try:
                if isinstance(item, TranscriptCorrection):
                    await self._correct.execute(project_id, item.turn_id, item.text)
                    continue
                directed = await self._direct.execute(project_id, item)
                for shot in directed.revised:
                    await self._events.publish(project_id, ShotUpdated(shot))
                for shot in directed.shots:
                    shots += 1
                    await self._events.publish(project_id, ShotCreated(shot))
                if directed.refusal:
                    await self._events.publish(project_id, SessionFailed(directed.refusal))
                if directed.capped and self._limits and not told_full:
                    told_full = True
                    await self._events.publish(project_id, SessionFailed(self._limits.shots_full))
                if directed.new_characters or directed.new_looks:
                    sheets = [*(c.id for c in directed.new_characters), *directed.new_looks]
                    await self._cast.execute(project_id, sheets)
            except ApplicationError as e:
                await self._events.publish(project_id, SessionFailed(e.user_message, source="director"))
            except DomainError:
                failed = CORRECTION_FAILED if isinstance(item, TranscriptCorrection) else DIRECTION_FAILED
                await self._events.publish(project_id, SessionFailed(failed, source="director"))
        return shots
