"""The animatic: panels timed to the narration, with the narrator's own voice (ADR 0011)."""

from __future__ import annotations

import hashlib

from frameteller.application.events import JobUpdated
from frameteller.application.jobs import EXPORT_ANIMATIC, export_job
from frameteller.application.ports import (
    EventPublisher,
    JobQueuePort,
    MediaStoragePort,
    ProjectRepository,
    VideoRendererPort,
)
from frameteller.application.use_cases.requests import JobTicket
from frameteller.domain import Animatic, AnimaticExport, MediaRef, Project

PROGRESS_STEP = 0.05  # publish progress every 5% of the timeline


def animatic_digest(animatic: Animatic, subtitles: bool) -> str:
    """Same panels, timing, voice and options: the same video, so it is rendered once."""
    return hashlib.sha256(repr((animatic, subtitles)).encode()).hexdigest()[:16]


class RequestAnimaticExport:
    """Check every shot has a panel, then queue the export. Progress arrives as job.updated."""

    def __init__(self, repo: ProjectRepository, jobs: JobQueuePort) -> None:
        self._repo, self._jobs = repo, jobs

    async def execute(self, project_id: str, *, subtitles: bool = False) -> JobTicket:
        animatic = Animatic.from_project(await self._repo.get(project_id))  # refuses early if a panel is missing
        job = export_job(project_id, animatic_digest(animatic, subtitles), subtitles)
        return JobTicket.of(job, await self._jobs.enqueue(job))


class ExportAnimatic:
    """Background job: render the MP4 and keep it as the project's animatic."""

    def __init__(
        self,
        repo: ProjectRepository,
        storage: MediaStoragePort,
        renderer: VideoRendererPort,
        events: EventPublisher,
    ) -> None:
        self._repo, self._storage, self._renderer, self._events = repo, storage, renderer, events

    async def execute(self, project_id: str, *, subtitles: bool = False, job_key: str = "") -> AnimaticExport:
        animatic = Animatic.from_project(await self._repo.get(project_id))
        frames = {c.shot_id: await self._storage.get(c.image) for c in animatic.clips}
        recordings = {}
        for cut in (cut for clip in animatic.clips for cut in clip.audio):
            if cut.recording.key not in recordings:
                recordings[cut.recording.key] = await self._storage.get(cut.recording)
        reported = 0.0

        async def on_progress(done: float) -> None:
            nonlocal reported
            if done - reported >= PROGRESS_STEP and done < 1:
                reported = done
                await self._events.publish(
                    project_id, JobUpdated(EXPORT_ANIMATIC, job_key, "running", progress=round(done, 2))
                )

        video = await self._renderer.render(animatic, frames, recordings, subtitles=subtitles, on_progress=on_progress)
        digest = animatic_digest(animatic, subtitles)
        ref = await self._storage.put(f"projects/{project_id}/exports/animatic-{digest}.mp4", video, "video/mp4")
        export = AnimaticExport(ref, animatic.duration_ms, subtitles, animatic.has_voice)

        def apply(project: Project) -> MediaRef | None:
            return project.record_animatic(export)

        replaced = await self._repo.update(project_id, apply)
        if replaced is not None:
            await self._storage.delete(replaced)  # the previous export: one animatic per project
        return export
