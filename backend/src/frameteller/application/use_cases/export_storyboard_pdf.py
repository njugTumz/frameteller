from __future__ import annotations

from frameteller.application.ports import MediaStoragePort, ProjectRepository, SheetRow, StoryboardSheetPort
from frameteller.domain import PanelNotReadyError, PanelStatus


class ExportStoryboardPdf:
    """The storyboard sheet: every shot in order, drawn or not, so it can go to print or a pitch at any time."""

    def __init__(self, repo: ProjectRepository, storage: MediaStoragePort, sheet: StoryboardSheetPort) -> None:
        self._repo, self._storage, self._sheet = repo, storage, sheet

    async def execute(self, project_id: str) -> bytes:
        project = await self._repo.get(project_id)
        if not project.shots:
            raise PanelNotReadyError("nothing to print: the project has no shots")
        rows = []
        for shot in project.shots:
            panel = project.panels.get(shot.id)
            shown = panel.shown_image if panel is not None and panel.status is PanelStatus.READY else None
            image = await self._storage.get(shown) if shown is not None else None
            framing = shot.framing.value.replace("_", " ")
            rows.append(SheetRow(shot.number, framing, shot.action, shot.dialogue, shot.duration_ms, image))
        return await self._sheet.render(project.title, rows)
