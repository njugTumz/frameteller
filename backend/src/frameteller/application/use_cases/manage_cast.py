"""Fix the cast after the fact: rename, remove, or merge a character that was cast twice."""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.application.jobs import panel_job
from frameteller.application.ports import JobQueuePort, ProjectRepository
from frameteller.application.use_cases.requests import JobTicket
from frameteller.domain import Project


class RenameCharacter:
    """A new name for a character. Its sheet and the cast's approval stand."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(self, project_id: str, character_id: str, name: str) -> Project:
        def apply(project: Project) -> Project:
            project.rename_character(character_id, name)
            return project

        return await self._repo.update(project_id, apply)


class RemoveCharacter:
    """Take a character out of the cast and out of every shot. Shots keep their action; their panels are outdated."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(self, project_id: str, character_id: str) -> Project:
        def apply(project: Project) -> Project:
            project.remove_character(character_id)
            return project

        return await self._repo.update(project_id, apply)


@dataclass(frozen=True, slots=True)
class Merged:
    project: Project
    redrawing: tuple[JobTicket, ...]  # draft re-renders of panels that showed the merged character


class MergeCharacters:
    """One character was cast twice: rebind its shots to the other and redraw their panels as drafts.

    Panels are redrawn only when the cast is approved; otherwise they are drawn after approval as usual.
    """

    def __init__(self, repo: ProjectRepository, jobs: JobQueuePort) -> None:
        self._repo, self._jobs = repo, jobs

    async def execute(self, project_id: str, character_id: str, into: str) -> Merged:
        def apply(project: Project) -> tuple[Project, list[tuple[str, int]]]:
            changed = project.merge_character(character_id, into)
            redraw = []
            if project.bible.is_approved:
                for shot in changed:
                    panel = project.panels.get(shot.id)
                    if panel is not None and panel.revision > 0:
                        redraw.append((shot.id, panel.revision + 1))
            return project, redraw

        project, redraw = await self._repo.update(project_id, apply)
        tickets = []
        for shot_id, revision in redraw:
            job = panel_job(project_id, shot_id, revision, "low")
            tickets.append(JobTicket.of(job, await self._jobs.enqueue(job)))
        return Merged(project, tuple(tickets))
