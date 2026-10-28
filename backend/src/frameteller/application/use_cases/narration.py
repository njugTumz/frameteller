from __future__ import annotations

from frameteller.application.ports import MediaStoragePort, ProjectRepository
from frameteller.domain import MediaRef, Project


class DeleteNarration:
    """ "Delete my recording": every kept session recording of the project. The animatic is then silent."""

    def __init__(self, repo: ProjectRepository, storage: MediaStoragePort) -> None:
        self._repo, self._storage = repo, storage

    async def execute(self, project_id: str) -> Project:
        def apply(project: Project) -> tuple[Project, list[MediaRef]]:
            return project, project.forget_narrations()

        project, recordings = await self._repo.update(project_id, apply)
        for ref in recordings:  # after the project forgets them, so a failure here leaves no dangling reference
            await self._storage.delete(ref)
        return project
