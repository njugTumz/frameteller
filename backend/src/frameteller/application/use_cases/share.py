"""Read-only share links: unguessable, revocable, and never revealing the project id."""

from __future__ import annotations

from frameteller.application.errors import ProjectNotFoundError, ShareNotFoundError
from frameteller.application.ports import (
    IdGenerator,
    MediaStoragePort,
    ProjectRepository,
    ShareIndex,
    SharePreviewPort,
)
from frameteller.domain import PanelStatus, Project

PREVIEW_PANELS = 6


class ShareProject:
    def __init__(self, repo: ProjectRepository, index: ShareIndex, ids: IdGenerator) -> None:
        self._repo, self._index, self._ids = repo, index, ids

    async def execute(self, project_id: str) -> str:
        offered = self._ids.new_id()
        token = await self._repo.update(project_id, lambda p: p.share(offered))
        await self._index.put(token, project_id)  # again for an existing link: repairs a lost index entry
        return token


class RevokeShare:
    def __init__(self, repo: ProjectRepository, index: ShareIndex) -> None:
        self._repo, self._index = repo, index

    async def execute(self, project_id: str) -> None:
        token = await self._repo.update(project_id, lambda p: p.unshare())
        if token is not None:
            await self._index.delete(token)


class OpenShare:
    """The project behind a live share link. A revoked or unknown token is simply not found."""

    def __init__(self, repo: ProjectRepository, index: ShareIndex) -> None:
        self._repo, self._index = repo, index

    async def execute(self, token: str) -> Project:
        project_id = await self._index.find(token)
        if project_id is None:
            raise ShareNotFoundError(token)
        try:
            project = await self._repo.get(project_id)
        except ProjectNotFoundError:
            raise ShareNotFoundError(token) from None
        if project.share_token != token:  # revoked, even if the index entry lingered
            raise ShareNotFoundError(token)
        return project


class SharePreview:
    """The link preview image: the first panels that are drawn, as one contact sheet."""

    def __init__(self, open_share: OpenShare, storage: MediaStoragePort, preview: SharePreviewPort) -> None:
        self._open, self._storage, self._preview = open_share, storage, preview

    async def execute(self, token: str) -> bytes:
        project = await self._open.execute(token)
        panels = []
        for shot in project.shots:
            panel = project.panels.get(shot.id)
            if panel is not None and panel.status is PanelStatus.READY and panel.shown_image is not None:
                panels.append(await self._storage.get(panel.shown_image))
            if len(panels) == PREVIEW_PANELS:
                break
        return await self._preview.contact_sheet(project.title, panels)
