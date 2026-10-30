from __future__ import annotations

import logging

from frameteller.application import costs
from frameteller.application.errors import ApplicationError, ModelContentFilteredError
from frameteller.application.image_safety import suggest_clothes, suggest_description
from frameteller.application.jobs import sheet_review_job
from frameteller.application.ports import (
    BudgetGuard,
    ImageGenerationPort,
    ImageRequest,
    JobQueuePort,
    ProjectRepository,
)
from frameteller.application.prompts import look_reference_prompt, reference_prompt
from frameteller.domain import Character, Look, Project, SheetRefusal, sheet_target

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

    async def execute(
        self, project_id: str, character_id: str, correction: str = "", look_id: str | None = None
    ) -> Character:
        """`look_id`: the sheet of that outfit (ADR 0018), drawn from the everyday sheet when there is one."""
        snapshot = await self._repo.get(project_id)
        drawn = snapshot.bible.get(character_id)
        look = drawn.look(look_id) if look_id else None
        target = sheet_target(character_id, look_id)
        await self._budget.charge(project_id, costs.IMAGE, f"reference {target}")
        store_as = f"projects/{project_id}/characters/{character_id}/" + (f"looks/{look_id}" if look else "reference")
        references = (drawn.reference,) if look and drawn.reference else ()

        def prompt(safer: bool) -> str:
            if look is not None:
                return look_reference_prompt(drawn, look, snapshot.style, correction, safer=safer)
            return reference_prompt(drawn, snapshot.style, correction, safer=safer)

        try:
            # SafeImages cleans the prompt and, if the content filter refuses it, tries the safer wording once
            # (ADR 0019). Refused prompts are not billed, so the one charge covers both.
            stored = await self._images.generate(
                ImageRequest(prompt(False), "high", "square", references, fallback_prompt=prompt(True)),
                store_as=store_as,
            )
        except ModelContentFilteredError as e:
            text = look.clothes if look else drawn.canonical_description
            suggestion = suggest_clothes(text) if look else suggest_description(text)
            reason = "Muse Image's safety filter turned it down twice. Use the suggested description, or edit it."

            def refused(p: Project) -> None:
                p.sheet_failures[target] = reason
                p.sheet_refusals[target] = SheetRefusal(text, suggestion)

            await self._repo.update(project_id, refused)
            log.warning("sheet refused twice by the content filter", extra={"sheet": target})
            raise SheetFailedError(f"{drawn.name} ({look.label})" if look else drawn.name, reason) from e
        except ApplicationError as e:
            message = e.user_message
            await self._repo.update(project_id, lambda p: p.sheet_failures.__setitem__(target, message))
            raise SheetFailedError(f"{drawn.name} ({look.label})" if look else drawn.name, message) from e

        def apply(project: Project) -> Character:
            current = project.bible.get(character_id)
            # If the description changed while drawing, this sheet shows the old one: keep it off the cast.
            if look is not None:
                if current.has_look(look.id) and _same_outfit(current.look(look.id), look):
                    project.bible.set_look_reference(character_id, look.id, stored.ref)
                    project.sheet_failures.pop(target, None)
                    project.sheet_refusals.pop(target, None)
            elif current.canonical_description == drawn.canonical_description:
                project.bible.set_reference(character_id, stored.ref)
                project.sheet_failures.pop(character_id, None)
                project.sheet_refusals.pop(character_id, None)
            return project.bible.get(character_id)

        character = await self._repo.update(project_id, apply)
        if self._jobs and snapshot.continuity_checks and look is None and character.reference == stored.ref:
            await self._jobs.enqueue(sheet_review_job(project_id, character_id, stored.ref.key))
        return character


def _same_outfit(current: Look, drawn: Look) -> bool:
    return current.clothes == drawn.clothes
