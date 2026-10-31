"""The animatic: panels timed to the narration, with the narrator's own voice (ADR 0011), and captions of what
is said: burned in by default, always as a soft track and an .srt file, translated by Muse Spark on request."""

from __future__ import annotations

import dataclasses
import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from frameteller.application import costs
from frameteller.application.events import JobUpdated
from frameteller.application.jobs import EXPORT_ANIMATIC, export_job
from frameteller.application.limits import EXPORTS, ProjectAllowance
from frameteller.application.ports import (
    BudgetGuard,
    CaptionTrack,
    EventPublisher,
    JobQueuePort,
    MediaStoragePort,
    ProjectRepository,
    SpeechSynthesisPort,
    TranslatorPort,
    VideoRendererPort,
)
from frameteller.application.use_cases.requests import JobTicket
from frameteller.application.use_cases.voices import DEFAULT_VOICE
from frameteller.domain import (
    TITLE_MS,
    Animatic,
    AnimaticExport,
    AudioCut,
    MediaRef,
    Project,
    caption_cues,
    script_language,
    to_srt,
)

log = logging.getLogger("frameteller.export")

PROGRESS_STEP = 0.05  # publish progress every 5% of the timeline
# The languages the renderer has fonts for (Latin, CJK, Devanagari, Arabic). Others are a soft track and an .srt.
BURNABLE = ("en", "fr", "es", "pt", "hi", "ar", "ja", "ko", "zh")
Audio = Literal["mine", "voice", "none"]
GALLERY_VOICE = DEFAULT_VOICE  # "the Ava voice instead": speaks every language we offer


@dataclass(frozen=True, slots=True)
class AnimaticOptions:
    subtitles: bool = True  # burn the captions into the picture
    caption_language: str | None = None  # a locale to translate the captions into; None: as spoken
    audio: Audio = "mine"  # the kept narration, the Ava voice reading the captions, or silent

    def payload(self) -> dict[str, str]:
        return {
            "subtitles": "1" if self.subtitles else "",
            "caption_language": self.caption_language or "",
            "audio": self.audio,
        }

    @classmethod
    def of(cls, payload: dict[str, str]) -> AnimaticOptions:
        raw = payload.get("audio")
        audio: Audio = "none" if raw == "none" else "voice" if raw == "voice" else "mine"
        return cls(bool(payload.get("subtitles")), payload.get("caption_language") or None, audio)


def animatic_digest(animatic: Animatic, options: AnimaticOptions) -> str:
    """Same panels, timing, voice and options: the same video, so it is rendered once."""
    return hashlib.sha256(repr((animatic, options)).encode()).hexdigest()[:16]


def spoken_language(project: Project) -> str:
    """What the turns are in: the language a voice read or the narrator chose, else what their script shows
    (Japanese, Korean, Chinese, Arabic, Hindi), else English."""
    chosen = next((n.language for n in project.narrations.values() if n.language), None)
    return chosen or script_language(" ".join(t.text for t in project.turns)) or "en-US"


def _silent(animatic: Animatic) -> Animatic:
    return dataclasses.replace(animatic, clips=tuple(dataclasses.replace(c, audio=()) for c in animatic.clips))


class RequestAnimaticExport:
    """Check every shot has a panel, then queue the export. Progress arrives as job.updated."""

    def __init__(self, repo: ProjectRepository, jobs: JobQueuePort, allowance: ProjectAllowance | None = None) -> None:
        self._repo, self._jobs, self._allowance = repo, jobs, allowance

    async def execute(self, project_id: str, options: AnimaticOptions | None = None) -> JobTicket:
        options = options or AnimaticOptions()
        project = await self._repo.get(project_id)
        animatic = Animatic.from_project(project)  # refuses early if a panel is missing
        if self._allowance:
            self._allowance.check(project, EXPORTS)
        job = export_job(project_id, animatic_digest(animatic, options), options.payload())
        enqueued = await self._jobs.enqueue(job)
        if enqueued and self._allowance:
            await self._allowance.spend(project_id, EXPORTS)
        return JobTicket.of(job, enqueued)


class ExportAnimatic:
    """Background job: render the MP4 and its captions, and keep them as the project's animatic."""

    def __init__(
        self,
        repo: ProjectRepository,
        storage: MediaStoragePort,
        renderer: VideoRendererPort,
        events: EventPublisher,
        translator: TranslatorPort | None = None,
        budget: BudgetGuard | None = None,
        synthesizer: SpeechSynthesisPort | None = None,
    ) -> None:
        self._repo, self._storage, self._renderer, self._events = repo, storage, renderer, events
        self._translator, self._budget, self._synthesizer = translator, budget, synthesizer

    async def execute(
        self, project_id: str, options: AnimaticOptions | None = None, *, job_key: str = ""
    ) -> AnimaticExport:
        options = options or AnimaticOptions()
        project = await self._repo.get(project_id)
        digest = animatic_digest(Animatic.from_project(project), options)

        async def on_progress(done: float) -> None:
            await self._events.publish(
                project_id, JobUpdated(EXPORT_ANIMATIC, job_key, "running", progress=round(done, 2))
            )

        export = await self.render(project, options, f"projects/{project_id}/exports/animatic-{digest}", on_progress)

        def apply(project: Project) -> AnimaticExport | None:
            previous = project.animatic
            project.record_animatic(export)
            return previous

        previous = await self._repo.update(project_id, apply)
        if previous is not None and previous.video != export.video:  # one animatic per project
            await self._storage.delete(previous.video)
            if previous.captions is not None and previous.captions != export.captions:
                await self._storage.delete(previous.captions)
        return export

    async def render(
        self,
        project: Project,
        options: AnimaticOptions,
        base: str,
        on_progress: Callable[[float], Awaitable[None]] | None = None,
    ) -> AnimaticExport:
        """Render and store `{base}.mp4` and `{base}.srt`, without recording them on the project (the gallery's
        copy uses this too)."""
        animatic = Animatic.from_project(project)
        language = spoken_language(project)
        if options.audio == "none":
            animatic = _silent(animatic)
        elif options.audio == "voice":
            animatic = await self._voiced(project.id, animatic, language, base)
        frames = {c.shot_id: await self._storage.get(c.image) for c in animatic.clips}
        recordings = {}
        for cut in (cut for clip in animatic.clips for cut in clip.audio):
            if cut.recording.key not in recordings:
                recordings[cut.recording.key] = await self._storage.get(cut.recording)
        language, texts = await self._captions(project.id, animatic, language, options)
        cues = tuple(caption_cues(animatic, texts, offset_ms=TITLE_MS))
        burn = options.subtitles and language.split("-")[0].lower() in BURNABLE
        track = CaptionTrack(cues, language, burn) if cues else None
        reported = 0.0

        async def progress(done: float) -> None:
            nonlocal reported
            if on_progress is not None and done - reported >= PROGRESS_STEP and done < 1:
                reported = done
                await on_progress(done)

        video = await self._renderer.render(animatic, frames, recordings, captions=track, on_progress=progress)
        if options.audio == "voice":  # the voice is in the video now
            for key in recordings:
                await self._storage.delete(MediaRef(key))
        ref = await self._storage.put(f"{base}.mp4", video, "video/mp4")
        srt = await self._storage.put(f"{base}.srt", to_srt(cues).encode(), "application/x-subrip") if cues else None
        translated = language if options.caption_language else ""
        return AnimaticExport(ref, animatic.duration_ms, burn, animatic.has_voice, srt, translated)

    async def _voiced(self, project_id: str, animatic: Animatic, language: str, base: str) -> Animatic:
        """Each shot's words read by the Ava voice, cut to the shot. Silent without Text-to-Speech."""
        if self._synthesizer is None:
            return _silent(animatic)
        clips = []
        for clip in animatic.clips:
            if not clip.caption.strip():
                clips.append(dataclasses.replace(clip, audio=()))
                continue
            if self._budget is not None:
                await self._budget.charge(project_id, costs.TTS_PER_CHARACTER * len(clip.caption), "gallery voice")
            spoken = await self._synthesizer.synthesize(
                clip.caption, GALLERY_VOICE, language, f"{base}-voice/{clip.shot_id}.wav"
            )
            cut = AudioCut(spoken.ref, 0, min(spoken.duration_ms, clip.duration_ms))
            clips.append(dataclasses.replace(clip, audio=(cut,)))
        return dataclasses.replace(animatic, clips=tuple(clips))

    async def _captions(
        self, project_id: str, animatic: Animatic, spoken: str, options: AnimaticOptions
    ) -> tuple[str, list[str]]:
        """The captions' language and text per clip: as spoken, or translated (falling back to as spoken)."""
        texts = [c.caption for c in animatic.clips]
        wanted = options.caption_language
        if not wanted or wanted.split("-")[0] == spoken.split("-")[0] or self._translator is None:
            return spoken, texts
        try:
            if self._budget is not None:
                await self._budget.charge(project_id, costs.TRANSLATION, "caption translation")
            indexed = [(i, t) for i, t in enumerate(texts) if t.strip()]
            done = await self._translator.translate([t for _, t in indexed], wanted)
        except Exception:
            log.warning("caption translation failed; captions stay as spoken", exc_info=True)
            return spoken, texts
        for (i, _), t in zip(indexed, done, strict=True):
            texts[i] = t
        return wanted, texts
