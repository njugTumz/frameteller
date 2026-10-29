from __future__ import annotations

from frameteller.application import costs
from frameteller.application.jobs import sheet_review_job
from frameteller.application.ports import (
    BudgetGuard,
    ImageGenerationPort,
    ImageRequest,
    JobQueuePort,
    ProjectRepository,
)
from frameteller.application.prompts import reference_prompt
from frameteller.domain import Character, Project


class GenerateCharacterReference:
    """Draw a reference sheet for one character. The cast goes back to draft until approved (ADR 0004)."""

    def __init__(
        self,
        repo: ProjectRepository,
        images: ImageGenerationPort,
        budget: BudgetGuard,
        jobs: JobQueuePort | None = None,
    ) -> None:
        self._repo, self._images, self._budget, self._jobs = repo, images, budget, jobs

    async def execute(self, project_id: str, character_id: str, correction: str = "") -> Character:
        snapshot = await self._repo.get(project_id)
        drawn = snapshot.bible.get(character_id)
        await self._budget.charge(project_id, costs.IMAGE, f"reference {character_id}")
        stored = await self._images.generate(
            ImageRequest(reference_prompt(drawn, snapshot.style, correction), "high", "square"),
            store_as=f"projects/{project_id}/characters/{character_id}/reference",
        )

        def apply(project: Project) -> Character:
            current = project.bible.get(character_id)
            # If the description changed while drawing, this sheet shows the old one: keep it off the cast.
            if current.canonical_description == drawn.canonical_description:
                project.bible.set_reference(character_id, stored.ref)
            return project.bible.get(character_id)

        character = await self._repo.update(project_id, apply)
        if self._jobs and snapshot.continuity_checks and character.reference == stored.ref:
            await self._jobs.enqueue(sheet_review_job(project_id, character_id, stored.ref.key))
        return character
