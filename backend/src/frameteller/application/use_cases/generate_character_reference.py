from __future__ import annotations

import logging

from frameteller.application import costs
from frameteller.application.errors import ApplicationError, ModelContentFilteredError
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

log = logging.getLogger("frameteller.cast")


class SheetFailedError(ApplicationError):
    """One character's sheet could not be drawn. The message names the character and says why."""

    def __init__(self, name: str, reason: str) -> None:
        super().__init__(f"{name}: {reason}")
        self.user_message = f"{name}'s sheet couldn't be drawn. {reason}"


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
        store_as = f"projects/{project_id}/characters/{character_id}/reference"
        try:
            try:
                prompt = reference_prompt(drawn, snapshot.style, correction)
                stored = await self._images.generate(ImageRequest(prompt, "high", "square"), store_as=store_as)
            except ModelContentFilteredError:
                # Refused prompts are not billed (Muse Image charges per image drawn), so one charge covers this.
                log.warning(
                    "sheet refused by the content filter; retrying by look and role", extra={"character": character_id}
                )
                prompt = reference_prompt(drawn, snapshot.style, correction, safer=True)
                stored = await self._images.generate(ImageRequest(prompt, "high", "square"), store_as=store_as)
        except ApplicationError as e:
            reason = (
                "Muse Image's safety filter turned it down. Describe them by look and role (no ages), then try again."
                if isinstance(e, ModelContentFilteredError)
                else e.user_message
            )
            await self._repo.update(project_id, lambda p: p.sheet_failures.__setitem__(character_id, reason))
            raise SheetFailedError(drawn.name, reason) from e

        def apply(project: Project) -> Character:
            current = project.bible.get(character_id)
            # If the description changed while drawing, this sheet shows the old one: keep it off the cast.
            if current.canonical_description == drawn.canonical_description:
                project.bible.set_reference(character_id, stored.ref)
                project.sheet_failures.pop(character_id, None)
            return project.bible.get(character_id)

        character = await self._repo.update(project_id, apply)
        if self._jobs and snapshot.continuity_checks and character.reference == stored.ref:
            await self._jobs.enqueue(sheet_review_job(project_id, character_id, stored.ref.key))
        return character
