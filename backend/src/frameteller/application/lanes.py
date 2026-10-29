"""Who a piece of work is for: a public visitor or a judge (the judge pass).

The interface sets the lane once per request or session from the judge cookie. Work started from there (queued
jobs, model calls, charges) inherits it, because asyncio tasks copy the context they were created in. Judges
skip the per-visitor caps and the waiting room, and spend from their own reserved daily budget.
"""

from __future__ import annotations

from contextvars import ContextVar
from enum import StrEnum


class Lane(StrEnum):
    PUBLIC = "public"
    JUDGE = "judge"


lane_var: ContextVar[Lane] = ContextVar("lane", default=Lane.PUBLIC)


def current_lane() -> Lane:
    return lane_var.get()


def is_judge() -> bool:
    return lane_var.get() is Lane.JUDGE
