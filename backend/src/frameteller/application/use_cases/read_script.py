"""ReadScript: "Read it to me" (ADR 0015). A voice reads the script while its shots are directed and drawn.

The user doesn't speak. Each paragraph is translated if needed, synthesized and stored, then published for the
browser to play; its turn lasts as long as its audio, so the animatic is timed to the synthesized narration.
Synthesis stays one paragraph ahead of playback. Between episodes the reading pauses until the episode's draft
panels are done (or the listener presses Continue), then goes on by itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import wave
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from frameteller.application import costs
from frameteller.application.audio import wav_bytes
from frameteller.application.errors import ApplicationError, InvalidModelOutputError
from frameteller.application.events import (
    ParagraphVoiced,
    ReadingPaused,
    ReadingResumed,
    ScriptAccepted,
    SessionEnded,
    SessionFailed,
    TurnFinished,
)
from frameteller.application.limits import SpeechAllowance
from frameteller.application.ports import (
    BudgetGuard,
    EventPublisher,
    IdGenerator,
    MediaStoragePort,
    ProjectRepository,
    SpeechSynthesisPort,
    TranslatorPort,
)
from frameteller.application.use_cases.story_director import StoryDirector, TranscriptCorrection
from frameteller.domain import MediaRef, Narration, PanelStatus, Project, Script, TranscriptTurn

ReadControl = Literal["pause", "continue"]
Sleep = Callable[[float], Awaitable[None]]

ENGLISH = "en"
LEAD_MS = 1500  # synthesize the next paragraph this long before the current one finishes playing
EPISODE_WAIT_S = 180  # the longest pause for an episode's drafts before reading on anyway
POLL_S = 2.0
TRANSLATION_FAILED = "We couldn't translate this episode, so it is read in the script's language."
KEEP_FAILED = "The narration was read, but we couldn't keep its audio for the animatic."


@dataclass(frozen=True, slots=True)
class ReadingOptions:
    voice: str
    language: str  # a locale: "en-US", "fr-FR"
    visitor: str | None = None


def speech_key(project_id: str, text: str, voice: str, language: str) -> str:
    """Where a paragraph's audio is cached: the same words in the same voice and language are never paid twice."""
    digest = hashlib.sha256(f"{voice}|{language}|{text}".encode()).hexdigest()[:24]
    return f"projects/{project_id}/speech/{digest}.wav"


def _pcm(data: bytes) -> tuple[bytes, int]:
    """The PCM frames of 24 kHz mono 16-bit WAV, and their length in ms."""
    with wave.open(io.BytesIO(data)) as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, 24_000):
            raise InvalidModelOutputError("azure-tts", "expected 24 kHz mono 16-bit PCM")
        frames = w.readframes(w.getnframes())
        return frames, w.getnframes() * 1000 // w.getframerate()


def drafts_done(project: Project, turn_ids: list[str]) -> bool:
    """Every turn was directed, and every shot from them has a drawn (or failed) panel."""
    directed = {t.id for t in project.turns}
    if not all(t in directed for t in turn_ids):
        return False
    for turn_id in turn_ids:
        for shot in project.shots_from_turn(turn_id):
            panel = project.panels.get(shot.id)
            if panel is None or panel.status == PanelStatus.PENDING:
                return False
    return True


class _Controls:
    """The listener's Pause and Continue, and whether they have left."""

    def __init__(self) -> None:
        self.running = asyncio.Event()
        self.running.set()
        self.resumed = asyncio.Event()  # a Continue since the last pause
        self.ended = False

    async def follow(self, controls: AsyncIterator[ReadControl]) -> None:
        try:
            async for c in controls:
                if c == "pause":
                    self.running.clear()
                    self.resumed.clear()
                else:
                    self.running.set()
                    self.resumed.set()
        finally:
            self.ended = True
            self.running.set()
            self.resumed.set()


class ReadScript:
    def __init__(
        self,
        speech: SpeechSynthesisPort,
        translator: TranslatorPort,
        story: StoryDirector,
        events: EventPublisher,
        ids: IdGenerator,
        repo: ProjectRepository,
        storage: MediaStoragePort,
        budget: BudgetGuard,
        allowance: SpeechAllowance | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._speech, self._translator, self._story = speech, translator, story
        self._events, self._ids, self._repo, self._storage = events, ids, repo, storage
        self._budget, self._allowance, self._sleep = budget, allowance, sleep

    async def execute(
        self, project_id: str, script: Script, options: ReadingOptions, controls: AsyncIterator[ReadControl]
    ) -> SessionEnded:
        tag = self._ids.new_id()[:8]
        work: asyncio.Queue[TranscriptTurn | TranscriptCorrection | None] = asyncio.Queue()
        state = _Controls()
        await self._events.publish(project_id, ScriptAccepted(script))
        director = asyncio.create_task(self._story.run(project_id, work))
        listener = asyncio.create_task(state.follow(controls))
        pcm = bytearray()
        turns: list[str] = []
        try:
            await self._read(project_id, tag, script, options, state, work, pcm, turns)
        except ApplicationError as e:
            await self._events.publish(project_id, SessionFailed(e.user_message, fatal=True))
        except BaseException:
            director.cancel()
            raise
        finally:
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener
        work.put_nowait(None)
        shots = await director
        if pcm:
            await self._keep(project_id, tag, bytes(pcm), options)
        ended = SessionEnded(len(turns), shots, bool(turns))
        await self._events.publish(project_id, ended)
        return ended

    async def _read(
        self,
        project_id: str,
        tag: str,
        script: Script,
        options: ReadingOptions,
        state: _Controls,
        work: asyncio.Queue[TranscriptTurn | TranscriptCorrection | None],
        pcm: bytearray,
        turns: list[str],
    ) -> None:
        """Voice the script in order, appending each turn's id to `turns` (kept if the reading stops early)."""
        index = 0
        playing_ms = 0  # the clip before the newest one: the browser is playing it now
        episode_turns: list[str] = []
        for episode in script.episodes:
            if index:  # between episodes: let the drafts catch up before reading on
                await self._sleep(playing_ms / 1000)  # the browser finishes the episode first
                await self._between_episodes(project_id, index, episode.number, state, episode_turns)
                playing_ms = 0
            episode_turns = []
            spoken = await self._spoken(project_id, [b.narration for b in episode.beats], options.language)
            for beat, text in zip(episode.beats, spoken, strict=True):
                if state.ended:
                    return
                if not state.running.is_set():
                    await self._events.publish(project_id, ReadingPaused(index, episode.number, "user"))
                    await state.running.wait()
                    if state.ended:
                        return
                    await self._events.publish(project_id, ReadingResumed(index))
                    playing_ms = 0  # the browser finished playing before the pause
                frames, duration = await self._voice(project_id, text, options)
                start = len(pcm) // 48
                pcm.extend(frames)
                ref = MediaRef(speech_key(project_id, text, options.voice, options.language))
                await self._events.publish(
                    project_id, ParagraphVoiced(index, episode.number, text, beat.narration, ref, duration)
                )
                direction = beat.direction or beat.narration  # the director reads the script's own words
                turn = TranscriptTurn(
                    f"{tag}-b{len(turns) + 1}", text, start, start + duration, None, direction, episode.number
                )
                await self._events.publish(project_id, TurnFinished(turn))
                work.put_nowait(turn)
                turns.append(turn.id)
                episode_turns.append(turn.id)
                index += 1
                # One paragraph ahead: the next is voiced just before the clip playing now ends.
                await self._sleep(max(0, playing_ms - LEAD_MS) / 1000)
                playing_ms = duration

    async def _between_episodes(
        self, project_id: str, next_paragraph: int, next_episode: int, state: _Controls, turn_ids: list[str]
    ) -> None:
        """ "Episode N is next": wait for the finished episode's drafts, a Continue, or EPISODE_WAIT_S."""
        await self._events.publish(project_id, ReadingPaused(next_paragraph, next_episode, "episode"))
        state.resumed.clear()
        waited = 0.0
        while not state.ended and not state.resumed.is_set() and waited < EPISODE_WAIT_S:
            if state.running.is_set() and drafts_done(await self._repo.get(project_id), turn_ids):
                break
            await self._sleep(POLL_S)
            waited += POLL_S
        await state.running.wait()  # a listener's Pause during the wait still holds the reading
        if not state.ended:
            await self._events.publish(project_id, ReadingResumed(next_paragraph))

    async def _spoken(self, project_id: str, texts: list[str], language: str) -> list[str]:
        """What the voice says: the script's words, translated by Spark unless the language is English."""
        if language.split("-")[0].lower() == ENGLISH:
            return texts
        try:
            return await self._translator.translate(texts, language)
        except ApplicationError:
            await self._events.publish(project_id, SessionFailed(TRANSLATION_FAILED))
            return texts

    async def _voice(self, project_id: str, text: str, options: ReadingOptions) -> tuple[bytes, int]:
        key = speech_key(project_id, text, options.voice, options.language)
        ref = MediaRef(key)
        if not await self._storage.exists(ref):
            if self._allowance:
                await self._allowance.take(options.visitor, len(text))
            await self._budget.charge(project_id, costs.tts(len(text)), f"speech {key.rsplit('/', 1)[-1]}")
            await self._speech.synthesize(text, options.voice, options.language, key)
        return _pcm(await self._storage.get(ref))

    async def _keep(self, project_id: str, tag: str, pcm: bytes, options: ReadingOptions) -> None:
        """The whole reading as one WAV: turn times are positions in it, as for a recorded narration."""
        try:
            ref = await self._storage.put(f"projects/{project_id}/narration/{tag}.wav", wav_bytes(pcm), "audio/wav")
            narration = Narration(tag, ref, len(pcm) // 48, options.voice, options.language)
            await self._repo.update(project_id, lambda p: p.keep_narration(narration))
        except Exception:
            await self._events.publish(project_id, SessionFailed(KEEP_FAILED))
