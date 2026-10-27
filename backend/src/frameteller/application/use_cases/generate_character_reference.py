from __future__ import annotations

from frameteller.application import costs
from frameteller.application.ports import (
    BudgetGuard,
    ImageGenerationPort,
    ImageRequest,
    ProjectRepository,
)
from frameteller.application.prompts import reference_prompt
from frameteller.domain import MediaRef


class GenerateCharacterReference:
    """Draw a reference sheet for one character. The cast goes back to draft until approved (ADR 0004)."""

    def __init__(self, repo: ProjectRepository, images: ImageGenerationPort, budget: BudgetGuard) -> None:
        self._repo, self._images, self._budget = repo, images, budget

    async def execute(self, project_id: str, character_id: str) -> MediaRef:
        project = await self._repo.get(project_id)
        character = project.bible.get(character_id)
        await self._budget.charge(project_id, costs.IMAGE, f"reference {character_id}")
        stored = await self._images.generate(
            ImageRequest(reference_prompt(character), "high", "square"),
            store_as=f"projects/{project_id}/characters/{character_id}/reference",
        )
        project.bible.set_reference(character_id, stored.ref)
        await self._repo.save(project)
        return stored.ref
