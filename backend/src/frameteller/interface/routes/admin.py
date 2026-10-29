"""The operator's API, behind ADMIN_TOKEN as a bearer token: today's budgets, the queues, and the gallery queue.

The admin page is https://app.frameteller.com/admin#<ADMIN_TOKEN>: the token stays in the fragment, so it never
reaches a server log, and the page sends it as `Authorization: Bearer`. Without ADMIN_TOKEN every route is 404.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from frameteller.application.lanes import Lane
from frameteller.interface.container import Container
from frameteller.interface.routes.deps import Deps

router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)


def require_admin(c: Deps, authorization: Annotated[str | None, Header()] = None) -> Container:
    token = c.settings.admin_token
    if token is None:
        raise HTTPException(404)
    expected = f"Bearer {token.get_secret_value()}"
    if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(401)
    return c


Admin = Annotated[Container, Depends(require_admin)]


class BudgetOut(BaseModel):
    lane: str
    day: str
    cap_usd: float
    spent_usd: float
    left_usd: float


class GateOut(BaseModel):
    name: str
    limit: int
    in_flight: int
    waiting: int
    hold_s: float
    longest_wait_s: float
    served: int
    waited: int
    max_waiting: int


class OverviewOut(BaseModel):
    paused: bool
    budgets: list[BudgetOut]
    gates: list[GateOut]
    live_sessions: int
    read_it_to_me: bool
    judge_pass: bool
    glimmer_warm_until: str | None


@router.get("/overview")
async def overview(c: Admin) -> OverviewOut:
    budgets = []
    for lane in (Lane.PUBLIC, Lane.JUDGE):
        s = await c.studio_status.execute(lane)
        budgets.append(
            BudgetOut(
                lane=lane.value,
                day=s.day,
                cap_usd=s.cap_usd,
                spent_usd=s.spent_usd,
                left_usd=round(max(0.0, s.cap_usd - s.spent_usd), 4),
            )
        )
    gates = [GateOut(**vars_of(g)) for g in [*c.capacity.states(), *(gate.state() for gate in c.jobs.gates())]]
    warm = await c.glimmer_lease.warm_until() if c.glimmer_lease is not None else None
    return OverviewOut(
        paused=c.settings.demo_paused,
        budgets=budgets,
        gates=gates,
        live_sessions=c.capacity.sessions.state().in_flight,
        read_it_to_me=c.read_script is not None,
        judge_pass=c.settings.judge_token is not None,
        glimmer_warm_until=warm.isoformat(timespec="seconds") if warm else None,
    )


def vars_of(state: object) -> dict[str, object]:
    return {name: getattr(state, name) for name in GateOut.model_fields}
