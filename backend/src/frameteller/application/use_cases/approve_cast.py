from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from frameteller.application.jobs import cast_job
from frameteller.application.ports import IdGenerator, JobQueuePort, ProjectRepository
from frameteller.domain import Project, sheet_target, split_target


@dataclass(frozen=True, slots=True)
class CastReview:
    approved: bool
    redrawing: tuple[str, ...] = ()  # sheets whose description changed and which are being redrawn
    job_key: str | None = None


class ApproveCast:
    """The user accepts the reference sheets, optionally correcting descriptions first (ADR 0004).

    Approval is a statement about the sheets the user saw. A corrected description invalidates its sheet, so
    the cast stays in draft, the sheet is redrawn in the background, and the user approves again. A description can
    be a look's clothes, keyed "wren/farmer_costume" (ADR 0018).
    """

    def __init__(self, repo: ProjectRepository, jobs: JobQueuePort, ids: IdGenerator) -> None:
        self._repo, self._jobs, self._ids = repo, jobs, ids

    async def execute(self, project_id: str, descriptions: Mapping[str, str] | None = None) -> CastReview:
        edits = {cid: text.strip() for cid, text in (descriptions or {}).items()}

        def apply(project: Project) -> tuple[str, ...]:
            changed = []
            for target, text in edits.items():
                cid, look_id = split_target(target)
                character = project.bible.get(cid)
                if look_id is not None:  # a look's clothes (ADR 0018)
                    if text and text != character.look(look_id).clothes:
                        project.restyle_look(cid, look_id, text)
                        changed.append(sheet_target(cid, look_id))
                elif text and text != character.canonical_description:
                    project.upsert_character(replace(character, canonical_description=text, reference=None))
                    changed.append(cid)
            if not changed:
                project.bible.approve()
            return tuple(changed)

        changed = await self._repo.update(project_id, apply)
        if not changed:
            return CastReview(approved=True)
        job = cast_job(project_id, changed, self._ids.new_id())
        await self._jobs.enqueue(job)
        return CastReview(approved=False, redrawing=changed, job_key=job.idempotency_key)
