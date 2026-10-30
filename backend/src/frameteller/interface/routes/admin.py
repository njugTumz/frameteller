"""The operator's API, behind ADMIN_TOKEN as a bearer token: today's budgets, the queues, and the gallery queue.

The admin page is https://app.frameteller.com/admin#<ADMIN_TOKEN>: the token stays in the fragment, so it never
reaches a server log, and the page sends it as `Authorization: Bearer`. Without ADMIN_TOKEN every route is 404.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, Field

from frameteller.application.lanes import Lane
from frameteller.application.use_cases.gallery import ModerateGallery
from frameteller.interface.container import Container
from frameteller.interface.dto import AdminGalleryAction, AdminGalleryEntryOut
from frameteller.interface.routes.deps import PROJECT_ID, Deps
from frameteller.interface.routes.media import serve

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
EntryId = Annotated[str, Path(pattern=PROJECT_ID)]


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


class JudgePassOut(BaseModel):
    pass_id: str
    first_seen: str
    stories_today: int
    spent_today_usd: float


class JudgeReserveOut(BaseModel):
    calendar_usd: float = Field(description="Today's reserve from the calendar (JUDGE_BUDGET_*).")
    override_usd: float | None = Field(description="The lower reserve set here; null: the calendar's applies.")
    stories_per_pass_per_day: int


class JudgeReserveIn(BaseModel):
    usd: float | None = Field(ge=0, description="A lower daily reserve for all judges; null clears it.")


class OverviewOut(BaseModel):
    paused: bool
    budgets: list[BudgetOut]
    gates: list[GateOut]
    live_sessions: int
    read_it_to_me: bool
    judge_pass: bool
    glimmer_warm_until: str | None
    judge_reserve: JudgeReserveOut
    judge_passes: list[JudgePassOut]


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
    states = [*c.capacity.states(), *(gate.state() for gate in c.jobs.gates())]
    gates = [GateOut.model_validate(g, from_attributes=True) for g in states]
    warm = await c.glimmer_lease.warm_until() if c.glimmer_lease is not None else None
    return OverviewOut(
        judge_reserve=await _reserve(c),
        judge_passes=[
            JudgePassOut.model_validate(p, from_attributes=True)
            for p in (await c.judge_passes.execute() if c.judge_passes else [])
        ],
        paused=c.settings.demo_paused,
        budgets=budgets,
        gates=gates,
        live_sessions=c.capacity.sessions.state().in_flight,
        read_it_to_me=c.read_script is not None,
        judge_pass=c.settings.judge_token is not None,
        glimmer_warm_until=warm.isoformat(timespec="seconds") if warm else None,
    )


async def _reserve(c: Container) -> JudgeReserveOut:
    calendar = c.settings.budget_calendar
    day = (await c.studio_status.execute(Lane.JUDGE)).day
    override = await c.judge_desk.reserve_override() if c.judge_desk else None
    return JudgeReserveOut(
        calendar_usd=calendar.cap(day, Lane.JUDGE),
        override_usd=override,
        stories_per_pass_per_day=c.settings.judge_stories_per_pass_per_day,
    )


@router.put("/judge/reserve")
async def set_judge_reserve(body: JudgeReserveIn, c: Admin) -> JudgeReserveOut:
    """Lower the judges' daily reserve now, without a redeploy (e.g. if the judge link leaks). It never raises it."""
    if c.judge_desk is None:
        raise HTTPException(404)
    await c.judge_desk.set_reserve(body.usd)
    return await _reserve(c)


# ---- the gallery (ADR 0017) ----


def _moderate(c: Container) -> ModerateGallery:
    if c.moderate_gallery is None:
        raise HTTPException(404)
    return c.moderate_gallery


@router.get("/gallery")
async def gallery_entries(c: Admin) -> list[AdminGalleryEntryOut]:
    """Every entry, newest first: pending ones, reports, and why the check held them."""
    return [AdminGalleryEntryOut.of(e) for e in await _moderate(c).entries()]


@router.post("/gallery/{entry_id}")
async def gallery_action(entry_id: EntryId, body: AdminGalleryAction, c: Admin) -> AdminGalleryEntryOut:
    """publish, hide, feature or unfeature."""
    return AdminGalleryEntryOut.of(await _moderate(c).act(entry_id, body.action))


@router.delete("/gallery/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def gallery_remove(entry_id: EntryId, c: Admin) -> None:
    await _moderate(c).remove(entry_id)


@router.get("/gallery/{entry_id}/video.mp4", response_class=Response)
async def gallery_video(entry_id: EntryId, request: Request, c: Admin) -> Response:
    """Any entry's video, pending or hidden ones too, for the admin to watch before deciding."""
    entry = next((e for e in await _moderate(c).entries() if e.id == entry_id), None)
    if entry is None or entry.video is None:
        raise HTTPException(404)
    return serve(await c.storage.get(entry.video), request, cache="private, no-store", filename="entry.mp4")
