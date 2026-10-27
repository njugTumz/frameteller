from __future__ import annotations

from frameteller.application import costs
from frameteller.application.ports import (
    BudgetGuard,
    ImageGenerationPort,
    ImageRequest,
    MediaStoragePort,
    ProjectRepository,
)
from frameteller.application.prompts import REFERENCE_SIZE, reference_prompt
from frameteller.domain import MediaRef


class GenerateCharacterReference:
    """Draw a reference sheet for one character. The cast goes back to draft until approved (ADR 0004)."""

    def __init__(
        self, repo: ProjectRepository, images: ImageGenerationPort, storage: MediaStoragePort, budget: BudgetGuard
    ) -> None:
        self._repo, self._images, self._storage, self._budget = repo, images, storage, budget

    async def execute(self, project_id: str, character_id: str) -> MediaRef:
        project = await self._repo.get(project_id)
        character = project.bible.get(character_id)
        await self._budget.charge(project_id, costs.IMAGE, f"reference {character_id}")
        image = await self._images.generate(ImageRequest(reference_prompt(character), REFERENCE_SIZE, "high"))
        ref = await self._storage.put(
            f"projects/{project_id}/characters/{character_id}/{image.response_id}", image.data, image.content_type
        )
        project.bible.set_reference(character_id, ref)
        await self._repo.save(project)
        return ref
