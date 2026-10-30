"""Edit the story after telling it: remove a beat said by mistake, merge two beats, delete a shot.

Each is one change to the project; the studio offers Undo by waiting 10 seconds before sending it.
"""

from __future__ import annotations

from typing import Literal

from frameteller.application.ports import ProjectRepository
from frameteller.domain import InvalidValueError, Project


class RemoveBeat:
    """A beat's words, the shots made only from it and their panels leave the story; the animatic and its captions
    no longer play that stretch of the recording."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(self, project_id: str, turn_id: str) -> Project:
        def apply(project: Project) -> Project:
            project.remove_turn(turn_id)
            return project

        return await self._repo.update(project_id, apply)


class MergeBeats:
    """Join a beat with the one before or after it. Their shots stay and share the merged time again."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(self, project_id: str, turn_id: str, other: Literal["previous", "next"]) -> Project:
        def apply(project: Project) -> Project:
            ids = [t.id for t in project.turns]
            project.turn(turn_id)
            at = ids.index(turn_id) + (-1 if other == "previous" else 1)
            if not 0 <= at < len(ids):
                raise InvalidValueError(f"there is no {other} beat to merge with")
            first, second = (ids[at], turn_id) if other == "previous" else (turn_id, ids[at])
            project.merge_turns(first, second)
            return project

        return await self._repo.update(project_id, apply)


class DeleteShot:
    """Delete one shot and its panel. Its words stay in the transcript; the animatic skips its stretch of voice."""

    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def execute(self, project_id: str, shot_id: str) -> Project:
        def apply(project: Project) -> Project:
            project.delete_shot(shot_id)
            return project

        return await self._repo.update(project_id, apply)
