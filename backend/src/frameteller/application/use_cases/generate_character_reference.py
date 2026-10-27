from __future__ import annotations

from frameteller.application import costs
from frameteller.application.ports import (
    BudgetGuard,
    ImageGenerationPort,
    ImageRequest,
    ProjectRepository,
)
from frameteller.application.prompts import reference_prompt
from frameteller.domain import Character, Project


class GenerateCharacterReference:
    """Draw a reference sheet for one character. The cast goes back to draft until approved (ADR 0004)."""

    def __init__(self, repo: ProjectRepository, images: ImageGenerationPort, budget: BudgetGuard) -> None:
        self._repo, self._images, self._budget = repo, images, budget

    async def execute(self, project_id: str, character_id: str) -> Character:
        drawn = (await self._repo.get(project_id)).bible.get(character_id)
        await self._budget.charge(project_id, costs.IMAGE, f"reference {character_id}")
        stored = await self._images.generate(
            ImageRequest(reference_prompt(drawn), "high", "square"),
            store_as=f"projects/{project_id}/characters/{character_id}/reference",
        )

        def apply(project: Project) -> Character:
            current = project.bible.get(character_id)
            # If the description changed while drawing, this sheet shows the old one: keep it off the cast.
            if current.canonical_description == drawn.canonical_description:
                project.bible.set_reference(character_id, stored.ref)
            return project.bible.get(character_id)

        return await self._repo.update(project_id, apply)
