from __future__ import annotations

import asyncio
from collections.abc import Sequence

from frameteller.application.events import CastProposed
from frameteller.application.ports import EventPublisher, ProjectRepository
from frameteller.application.use_cases.generate_character_reference import GenerateCharacterReference
from frameteller.domain import Character, split_target


class GenerateCastReferences:
    """Background job: draw sheets for several characters at once, then propose them for approval.

    A target is a character ("wren") or one of its looks ("wren/farmer_costume", ADR 0018). Everyday sheets come
    first, because a look is drawn from its character's everyday sheet. A character redrawn for a new
    description also gets the looks redrawn that lost their sheets with it, if some shot shows them.
    """

    def __init__(
        self, reference: GenerateCharacterReference, events: EventPublisher, repo: ProjectRepository | None = None
    ) -> None:
        self._reference, self._events, self._repo = reference, events, repo

    async def execute(self, project_id: str, targets: Sequence[str], correction: str = "") -> list[Character]:
        split = [split_target(t) for t in targets]
        bases = [cid for cid, look in split if look is None]
        results = await self._draw(project_id, [(cid, None) for cid in bases], correction)
        looks = [(cid, look) for cid, look in split if look is not None]
        if self._repo is not None and bases:
            project = await self._repo.get(project_id)
            for cid in bases:
                if cid in project.bible:
                    looks += [
                        (cid, lk.id) for lk in project.shown(project.bible.get(cid)).looks if lk.reference is None
                    ]
        results += await self._draw(project_id, list(dict.fromkeys(looks)), correction)
        drawn = list({r.id: r for r in results if isinstance(r, Character)}.values())
        if self._repo is not None and drawn:
            project = await self._repo.get(project_id)
            drawn = [project.shown(c) for c in drawn]  # the tray lists only the looks some shot shows
        if drawn:
            await self._events.publish(project_id, CastProposed(tuple(drawn)))
        for r in results:
            if isinstance(r, BaseException):
                raise r  # the job fails and reports it; the sheets that worked are already proposed
        return drawn

    async def _draw(
        self, project_id: str, sheets: list[tuple[str, str | None]], correction: str
    ) -> list[Character | BaseException]:
        return list(
            await asyncio.gather(
                *(self._reference.execute(project_id, cid, correction, look) for cid, look in sheets),
                return_exceptions=True,
            )
        )
