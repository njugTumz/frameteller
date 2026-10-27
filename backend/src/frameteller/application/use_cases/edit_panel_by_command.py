from __future__ import annotations

from frameteller.application.ports import DirectorPort, ProjectRepository
from frameteller.application.use_cases.edit_panel_appearance import EditPanelAppearance
from frameteller.domain import Panel


class EditPanelByCommand:
    """Background job: the director routes a free-form instruction into an appearance edit (ADR 0005)."""

    def __init__(self, repo: ProjectRepository, director: DirectorPort, edit: EditPanelAppearance) -> None:
        self._repo, self._director, self._edit = repo, director, edit

    async def execute(self, project_id: str, shot_id: str, instruction: str) -> Panel:
        project = await self._repo.get(project_id)
        shot = project.shot(shot_id)
        cast = [project.bible.get(cid) for cid in shot.character_ids]
        intent = await self._director.interpret_edit(instruction, shot, cast)
        return await self._edit.execute(project_id, shot_id, intent.target, intent.parts, intent.change)
