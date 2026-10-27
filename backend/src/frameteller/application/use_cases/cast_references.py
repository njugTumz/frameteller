from __future__ import annotations

import asyncio
from collections.abc import Sequence

from frameteller.application.events import CastProposed
from frameteller.application.ports import EventPublisher
from frameteller.application.use_cases.generate_character_reference import GenerateCharacterReference
from frameteller.domain import Character


class GenerateCastReferences:
    """Background job: draw sheets for several characters at once, then propose them for approval."""

    def __init__(self, reference: GenerateCharacterReference, events: EventPublisher) -> None:
        self._reference, self._events = reference, events

    async def execute(self, project_id: str, character_ids: Sequence[str]) -> list[Character]:
        results = await asyncio.gather(
            *(self._reference.execute(project_id, cid) for cid in character_ids), return_exceptions=True
        )
        drawn = [r for r in results if isinstance(r, Character)]
        if drawn:
            await self._events.publish(project_id, CastProposed(tuple(drawn)))
        for r in results:
            if isinstance(r, BaseException):
                raise r  # the job fails and reports it; the sheets that worked are already proposed
        return drawn
