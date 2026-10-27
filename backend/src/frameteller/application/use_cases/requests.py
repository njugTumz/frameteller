"""Commands that queue slow work and return at once (CLAUDE.md section 6: never block on image generation)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from frameteller.application.jobs import cast_job, edit_job, panel_job
from frameteller.application.ports import IdGenerator, Job, JobQueuePort, ProjectRepository, Quality
from frameteller.domain import InvalidValueError

MAX_INSTRUCTION_CHARS = 500


@dataclass(frozen=True, slots=True)
class JobTicket:
    kind: str
    key: str
    enqueued: bool  # False when the same job was already queued, running or done
    shot_id: str | None = None
    revision: int | None = None

    @classmethod
    def of(cls, job: Job, enqueued: bool) -> JobTicket:
        revision = job.payload.get("revision")
        return cls(
            job.kind, job.idempotency_key, enqueued, job.payload.get("shot_id"), int(revision) if revision else None
        )


class RequestPanelRender:
    """Queue the next revision of a shot's panel, as a draft (low) or final (high)."""

    def __init__(self, repo: ProjectRepository, jobs: JobQueuePort) -> None:
        self._repo, self._jobs = repo, jobs

    async def execute(self, project_id: str, shot_id: str, quality: Quality) -> JobTicket:
        project = await self._repo.get(project_id)
        project.require_cast_approved()  # fail now rather than in the background
        job = panel_job(project_id, shot_id, project.panel(shot_id).revision + 1, quality)
        return JobTicket.of(job, await self._jobs.enqueue(job))


class RequestPanelEdit:
    """Queue a spoken or typed appearance edit of a rendered panel."""

    def __init__(self, repo: ProjectRepository, jobs: JobQueuePort) -> None:
        self._repo, self._jobs = repo, jobs

    async def execute(self, project_id: str, shot_id: str, instruction: str) -> JobTicket:
        instruction = instruction.strip()
        if not instruction or len(instruction) > MAX_INSTRUCTION_CHARS:
            raise InvalidValueError(f"an edit instruction needs 1 to {MAX_INSTRUCTION_CHARS} characters")
        project = await self._repo.get(project_id)
        project.require_cast_approved()
        panel = project.panel(shot_id)
        panel.require_ready()
        job = edit_job(project_id, shot_id, panel.revision, instruction)
        return JobTicket.of(job, await self._jobs.enqueue(job))


class RequestCastReferences:
    """Queue reference sheets for characters: new ones from the director, or a deliberate regenerate."""

    def __init__(self, repo: ProjectRepository, jobs: JobQueuePort, ids: IdGenerator) -> None:
        self._repo, self._jobs, self._ids = repo, jobs, ids

    async def execute(self, project_id: str, character_ids: Sequence[str]) -> JobTicket:
        project = await self._repo.get(project_id)
        for cid in character_ids:
            project.bible.get(cid)  # unknown ids fail here, not in the background
        job = cast_job(project_id, character_ids, self._ids.new_id())
        return JobTicket.of(job, await self._jobs.enqueue(job))
