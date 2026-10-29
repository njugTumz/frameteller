"""Public-demo allowances (CLAUDE.md section 6, cost guardrails), on top of the spend budgets.

Per visitor (a hash of IP and browser id, never stored raw): new projects per day. Per project: shots, panel
renders and edits, and exports. Per live session: minutes of narration. Each refusal says what happened and
what to do next.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from frameteller.application.errors import LimitReachedError
from frameteller.application.ports import Clock, ProjectRepository, VisitorQuota
from frameteller.domain import Project

RENDERS = "renders"  # panel renders and appearance edits
EXPORTS = "exports"
PROJECTS = "projects"


@dataclass(frozen=True, slots=True)
class DemoLimits:
    projects_per_visitor_per_day: int = 3
    narration_ms_per_session: int = 3 * 60_000
    shots_per_project: int = 12
    renders_per_project: int = 30
    exports_per_project: int = 3

    def messages(self) -> dict[str, str]:
        return {
            PROJECTS: f"You've started {self.projects_per_visitor_per_day} stories today, the most for the public "
            "demo. Keep working on one of them, or come back tomorrow.",
            RENDERS: f"This story has used its {self.renders_per_project} drawings and edits for the public demo. "
            "Export the animatic or share it as it is.",
            EXPORTS: f"This story has been exported {self.exports_per_project} times, the most for the public demo. "
            "Download the animatic you have.",
        }

    @property
    def shots_full(self) -> str:
        return (
            f"This story has {self.shots_per_project} shots, the most for the public demo. Your storyboard is "
            "saved: draw, edit and export it."
        )

    @property
    def narration_full(self) -> str:
        minutes = self.narration_ms_per_session // 60_000
        return (
            f"That's {minutes} minutes, the longest telling the public demo allows. Your shots are saved; "
            "press Start telling to carry on."
        )


class ProjectAllowance:
    """Per-project allowances, counted in the project document so they survive restarts.

    `check` before queueing work, `spend` once a job was actually queued (a repeated request costs nothing).
    """

    def __init__(self, repo: ProjectRepository, limits: DemoLimits) -> None:
        self._repo, self._limits = repo, limits
        self._caps = {RENDERS: limits.renders_per_project, EXPORTS: limits.exports_per_project}

    def check(self, project: Project, kind: str) -> None:
        if project.usage.get(kind, 0) >= self._caps[kind]:
            raise LimitReachedError(self._limits.messages()[kind])

    async def spend(self, project_id: str, kind: str) -> None:
        await self._repo.update(project_id, lambda p: p.count_use(kind))


class VisitorAllowance:
    """Per-visitor daily allowances. One replica (ADR 0009), so a lock makes check-then-add atomic."""

    def __init__(self, quota: VisitorQuota, clock: Clock, limits: DemoLimits) -> None:
        self._quota, self._clock, self._limits = quota, clock, limits
        self._lock = asyncio.Lock()

    async def take(self, visitor: str, kind: str = PROJECTS) -> None:
        day = self._clock.now().date().isoformat()
        async with self._lock:
            if await self._quota.used(visitor, day, kind) >= self._limits.projects_per_visitor_per_day:
                raise LimitReachedError(self._limits.messages()[kind])
            await self._quota.add(visitor, day, kind)
