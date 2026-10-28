from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

from frameteller.application.errors import ApplicationError
from frameteller.application.events import SessionEnded, SessionFailed, ShotCreated, TranscriptUpdated, TurnFinished
from frameteller.application.ports import (
    AudioProgress,
    EventPublisher,
    IdGenerator,
    PartialTranscript,
    SpeechOptions,
    SpeechToTextPort,
    TurnCompleted,
    TurnEnded,
    TurnStarted,
)
from frameteller.application.use_cases.correct_transcript import CorrectTranscript
from frameteller.application.use_cases.direct_turn import DirectTurn
from frameteller.application.use_cases.requests import RequestCastReferences
from frameteller.domain import DomainError, TranscriptTurn

DIRECTION_FAILED = "The director couldn't place that line. Try saying it again."
CORRECTION_FAILED = "We couldn't apply that correction. Check the turn and try again."
AUDIO_BUFFER_FRAMES = 256  # about 20 s of 80 ms frames waiting for the transcriber
# A beat closes once the transcriber has processed this much audio past it (ADR 0008). The last word before a
# pause reached the transcript up to 240 ms after the pause; the next sentence's first word, 840 ms or more.
BEAT_GRACE_MS = 500


@dataclass(frozen=True, slots=True)
class Beat:
    """The narrator marked "a new shot starts now", `at_ms` into the audio they have sent (ADR 0008).

    It closes the stretch since the previous beat once the transcript has caught up with `at_ms`.
    """

    at_ms: int


@dataclass(frozen=True, slots=True)
class TranscriptCorrection:
    """The user fixed misheard words in a turn."""

    turn_id: str
    text: str


ClientInput = bytes | Beat | TranscriptCorrection


class _Heard:
    """Every word heard so far this session, and where the last shot boundary fell (ADR 0008).

    Partials are cumulative per transcriber turn, so the words of finished turns are kept and the current partial
    is appended. Closing a beat takes the words since the previous boundary. Beats are matched to the transcript by
    word position, so later rewording inside a closed beat cannot move words into the next one.

    A stretch starts where its first words were spoken (the transcriber's speechStart), not at the previous
    boundary: silence before them is trimmed, so a shot never lasts through a long pause before the narrator
    starts. A transcriber turn that began before the boundary is still going, so its words start at the boundary.
    """

    def __init__(self) -> None:
        self.done: list[str] = []
        self.partial: list[str] = []
        self.cursor = 0  # words before this index already belong to a directed turn
        self.cut_ms = 0  # the audio position of the last boundary
        self.speech_end_ms = 0
        self.speech_start_ms: int | None = None  # the latest transcriber turn's speechStart
        self.first_speech_ms: int | None = None  # where the open stretch's first words were spoken

    def hear_speech_start(self, start_ms: int) -> None:
        self.speech_start_ms = start_ms

    def _note_first_words(self) -> None:
        if self.first_speech_ms is None and len(self.done) + len(self.partial) > self.cursor:
            self.first_speech_ms = max(self.cut_ms, self.speech_start_ms or 0)

    @property
    def heard_any(self) -> bool:
        return bool(self.done or self.partial)

    def hear_partial(self, text: str) -> None:
        self.partial = text.split()
        self._note_first_words()

    def finish_turn(self, text: str) -> None:
        final = text.split()
        # The final text normally matches the last partial; keep whichever has more words so positions hold.
        self.done += final if len(final) >= len(self.partial) else self.partial
        self.partial = []
        self._note_first_words()

    def pending(self) -> str:
        """The words heard since the last boundary: the live line the narrator sees."""
        return " ".join((self.done + self.partial)[self.cursor :])

    def cut(self, at_ms: int) -> tuple[str, int, int]:
        """Close the stretch since the last boundary: (its text, start ms, end ms), leading silence trimmed."""
        words = self.done + self.partial
        text = " ".join(words[self.cursor :])
        self.cursor = max(self.cursor, len(words))
        start = self.cut_ms if self.first_speech_ms is None else self.first_speech_ms
        self.cut_ms = max(self.cut_ms, at_ms)
        self.first_speech_ms = None
        start = min(start, self.cut_ms)
        return text, start, max(at_ms, start)


async def _drain(audio: asyncio.Queue[bytes | None]) -> None:
    while await audio.get() is not None:
        pass


class RunVoiceSession:
    """Live narration: transcribe, direct each finished stretch into shots, and queue sheets for new characters.

    Shots are cut by the narrator's beats when they send them, otherwise by the transcriber's turns (ADR 0008).
    A beat closes as soon as the transcriber has processed BEAT_GRACE_MS of audio past it, so the last words before
    it are in. Once a beat has arrived, transcriber turns no longer create shots: the same audio is never directed
    twice.
    Direction runs one stretch at a time, in order, beside the stream (ADR 0002); a failure is reported and
    skipped, and the session carries on.
    """

    def __init__(
        self,
        speech: SpeechToTextPort,
        direct: DirectTurn,
        correct: CorrectTranscript,
        cast: RequestCastReferences,
        events: EventPublisher,
        ids: IdGenerator,
    ) -> None:
        self._speech, self._direct, self._correct = speech, direct, correct
        self._cast, self._events, self._ids = cast, events, ids

    async def execute(
        self, project_id: str, client: AsyncIterator[ClientInput], options: SpeechOptions
    ) -> SessionEnded:
        # Turn ids are per session; the tag keeps a second narration in the same project from reusing them.
        tag = self._ids.new_id()[:8]
        work: asyncio.Queue[TranscriptTurn | TranscriptCorrection | None] = asyncio.Queue()
        audio: asyncio.Queue[bytes | None] = asyncio.Queue(AUDIO_BUFFER_FRAMES)
        heard = _Heard()
        counts = {"beats": 0, "turns": 0, "shots": 0}
        beat_mode = False  # set by the first beat: from then on beats, not the transcriber, cut the shots
        beats: list[int] = []  # beats waiting for the transcript to catch up, oldest first

        async def publish_failure(message: str, *, fatal: bool = False) -> None:
            await self._events.publish(project_id, SessionFailed(message, fatal))

        async def finish(turn: TranscriptTurn) -> None:
            counts["turns"] += 1
            await self._events.publish(project_id, TurnFinished(turn))
            if turn.text.strip():
                work.put_nowait(turn)

        async def close_beat(at_ms: int) -> None:
            text, start, end = heard.cut(at_ms)
            if text:
                counts["beats"] += 1
                await finish(TranscriptTurn(f"{tag}-b{counts['beats']}", text, start, end))
                await self._events.publish(project_id, TranscriptUpdated(heard.pending()))

        async def close_beats_heard(processed_ms: int | None = None) -> None:
            """Close the waiting beats the transcript has caught up with (all of them when it has ended)."""
            while beats and (processed_ms is None or processed_ms >= beats[0] + BEAT_GRACE_MS):
                await close_beat(beats.pop(0))

        async def read_client() -> None:
            nonlocal beat_mode
            try:
                async for item in client:
                    if isinstance(item, Beat):
                        beat_mode = True
                        beats.append(item.at_ms)
                    elif isinstance(item, TranscriptCorrection):
                        work.put_nowait(item)
                    else:
                        await audio.put(item)
            except Exception:
                await audio.put(None)  # end the transcriber's input so the stream cannot wait forever
                raise
            await audio.put(None)

        async def pcm() -> AsyncIterator[bytes]:
            while (chunk := await audio.get()) is not None:
                yield chunk

        async def direct() -> None:
            while (item := await work.get()) is not None:
                try:
                    if isinstance(item, TranscriptCorrection):
                        await self._correct.execute(project_id, item.turn_id, item.text)
                        continue
                    directed = await self._direct.execute(project_id, item)
                    for shot in directed.shots:
                        counts["shots"] += 1
                        await self._events.publish(project_id, ShotCreated(shot))
                    if directed.new_characters:
                        await self._cast.execute(project_id, [c.id for c in directed.new_characters])
                except ApplicationError as e:
                    await publish_failure(e.user_message)
                except DomainError:
                    failed = CORRECTION_FAILED if isinstance(item, TranscriptCorrection) else DIRECTION_FAILED
                    await publish_failure(failed)

        director = asyncio.create_task(direct())
        reader = asyncio.create_task(read_client())
        try:
            async for event in self._speech.stream(pcm(), options):
                if isinstance(event, PartialTranscript):
                    heard.hear_partial(event.text)
                    await self._events.publish(project_id, TranscriptUpdated(heard.pending()))
                elif isinstance(event, AudioProgress):
                    await close_beats_heard(event.processed_ms)
                elif isinstance(event, TurnStarted):
                    heard.hear_speech_start(event.start_ms)
                elif isinstance(event, TurnEnded):
                    heard.speech_end_ms = max(heard.speech_end_ms, event.end_ms)
                elif isinstance(event, TurnCompleted):
                    heard.finish_turn(event.turn.text)
                    heard.speech_end_ms = max(heard.speech_end_ms, event.turn.end_ms)
                    if not beat_mode:  # endpointing is the fallback when the narrator sends no beats
                        heard.cut(event.turn.end_ms)
                        t = event.turn
                        await finish(TranscriptTurn(f"{tag}-{t.id}", t.text, t.start_ms, t.end_ms, t.speaker))
            # The transcriber has stopped reading: discard any audio left so the last beats can still be read.
            discard = asyncio.create_task(_drain(audio))
            await reader
            discard.cancel()
            if beat_mode:  # the transcript is complete: close every waiting beat, then the last stretch
                await close_beats_heard()
                await close_beat(max(heard.speech_end_ms, heard.cut_ms))
        except ApplicationError as e:
            await publish_failure(e.user_message, fatal=True)
        except BaseException:
            director.cancel()
            raise
        finally:
            if not reader.done():
                reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(reader, return_exceptions=True)
        work.put_nowait(None)
        await director  # finish directing what was said before the stream ended
        ended = SessionEnded(counts["turns"], counts["shots"])
        await self._events.publish(project_id, ended)
        return ended
