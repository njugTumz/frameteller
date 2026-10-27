from __future__ import annotations

from dataclasses import dataclass

from frameteller.application.events import ShotsReplaced
from frameteller.application.ports import DirectorPort, EventPublisher, IdGenerator, ProjectRepository
from frameteller.application.use_cases.direct_turn import add_new_characters, shots_for_turn
from frameteller.application.use_cases.requests import RequestCastReferences
from frameteller.domain import InvalidValueError, Project

MAX_TURN_CHARS = 2000


@dataclass(frozen=True, slots=True)
class _Redirected:
    event: ShotsReplaced
    new_character_ids: list[str]


class CorrectTranscript:
    """Fix misheard words in one turn and re-direct only the shots that came from it (ADR 0008).

    The new shots take the old shots' place in the storyboard; their panels are dropped because they showed the
    misheard version. New characters get reference sheets queued, as in a live session.
    """

    def __init__(
        self,
        repo: ProjectRepository,
        director: DirectorPort,
        ids: IdGenerator,
        cast: RequestCastReferences,
        events: EventPublisher,
    ) -> None:
        self._repo, self._director, self._ids, self._cast, self._events = repo, director, ids, cast, events

    async def execute(self, project_id: str, turn_id: str, text: str) -> ShotsReplaced:
        if len(text) > MAX_TURN_CHARS:
            raise InvalidValueError(f"a corrected turn has at most {MAX_TURN_CHARS} characters")
        snapshot = await self._repo.get(project_id)
        corrected = snapshot.correct_turn(turn_id, text)
        # The director sees the story without the misheard shots, so it does not copy them.
        snapshot.replace_shots([s.id for s in snapshot.shots_from_turn(turn_id)], [])
        directed = await self._director.direct_turn(corrected, snapshot)

        def apply(project: Project) -> _Redirected:
            turn = project.correct_turn(turn_id, text)
            old = [s.id for s in project.shots_from_turn(turn_id)]
            new = add_new_characters(project, directed.new_characters)
            shots = shots_for_turn(directed.shots, turn, self._ids, 1)
            placed = project.replace_shots(old, shots)
            return _Redirected(ShotsReplaced(turn, tuple(old), tuple(placed)), [c.id for c in new])

        done = await self._repo.update(project_id, apply)
        await self._events.publish(project_id, done.event)
        if done.new_character_ids:
            await self._cast.execute(project_id, done.new_character_ids)
        return done.event
