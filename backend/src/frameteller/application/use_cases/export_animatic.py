from __future__ import annotations

from frameteller.application.ports import MediaStoragePort, ProjectRepository, VideoRendererPort
from frameteller.domain import Animatic, MediaRef


class ExportAnimatic:
    """Render the MP4 animatic: one clip per shot, timed from the narration turns."""

    def __init__(self, repo: ProjectRepository, storage: MediaStoragePort, renderer: VideoRendererPort) -> None:
        self._repo, self._storage, self._renderer = repo, storage, renderer

    async def execute(self, project_id: str, narration: MediaRef | None = None) -> MediaRef:
        project = await self._repo.get(project_id)
        animatic = Animatic.from_project(project, narration)
        frames = {c.shot_id: await self._storage.get(c.image) for c in animatic.clips}
        audio = await self._storage.get(narration) if narration else None
        video = await self._renderer.render(animatic, frames, audio)
        return await self._storage.put(f"projects/{project_id}/exports/animatic.mp4", video, "video/mp4")
