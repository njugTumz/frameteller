from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, status

from frameteller.domain import Point, Size
from frameteller.interface.dto import (
    CastApproval,
    CastReviewOut,
    EditRequest,
    ErrorOut,
    ProjectCreate,
    ProjectOut,
    RenderRequest,
    ReorderRequest,
    SelectionOut,
    SelectRequest,
    ShotOut,
    ShotsOut,
    TicketOut,
)
from frameteller.interface.routes.deps import Deps, ProjectId

router = APIRouter(
    prefix="/projects", tags=["projects"], responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}}
)

ShotNumber = Annotated[int, Path(ge=1, le=10_000)]
CharacterId = Annotated[str, Path(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, c: Deps) -> ProjectOut:
    return ProjectOut.of(await c.create_project.execute(body.title))


@router.get("/{project_id}")
async def get_project(project_id: ProjectId, c: Deps) -> ProjectOut:
    return ProjectOut.of(await c.get_project.execute(project_id))


@router.post("/{project_id}/cast/approve")
async def approve_cast(project_id: ProjectId, body: CastApproval, c: Deps) -> CastReviewOut:
    """Approve the reference sheets, or correct descriptions first (those sheets are redrawn, cast stays draft)."""
    return CastReviewOut.of(await c.approve_cast.execute(project_id, body.descriptions))


@router.post("/{project_id}/cast/{character_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_reference(project_id: ProjectId, character_id: CharacterId, c: Deps) -> TicketOut:
    return TicketOut.of(await c.request_cast.execute(project_id, [character_id]))


@router.post(
    "/{project_id}/shots/{n}/panel", status_code=status.HTTP_202_ACCEPTED, responses={402: {"model": ErrorOut}}
)
async def render_panel(project_id: ProjectId, n: ShotNumber, body: RenderRequest, c: Deps) -> TicketOut:
    """Queue the next revision of shot n's panel. Progress arrives as job.updated events."""
    shot = await c.find_shot.execute(project_id, n)
    return TicketOut.of(await c.request_render.execute(project_id, shot.id, body.as_quality()))


@router.post("/{project_id}/shots/{n}/panel/edit", status_code=status.HTTP_202_ACCEPTED)
async def edit_panel(project_id: ProjectId, n: ShotNumber, body: EditRequest, c: Deps) -> TicketOut:
    """Queue an appearance edit ("her coat is red now"); the director routes it, Muse Image redraws."""
    shot = await c.find_shot.execute(project_id, n)
    return TicketOut.of(await c.request_edit.execute(project_id, shot.id, body.instruction))


@router.post("/{project_id}/shots/{n}/panel/select", responses={402: {"model": ErrorOut}, 422: {"model": ErrorOut}})
async def select_object(project_id: ProjectId, n: ShotNumber, body: SelectRequest, c: Deps) -> SelectionOut:
    """Select the object under a click. Pre-segmented masks answer at once (cached: true); otherwise SAM runs."""
    shot = await c.find_shot.execute(project_id, n)
    shown = Size(body.preview_width, body.preview_height)
    return SelectionOut.of(await c.select_object.execute(project_id, shot.id, Point(body.x, body.y), shown))


@router.post("/{project_id}/shots/reorder")
async def reorder_shots(project_id: ProjectId, body: ReorderRequest, c: Deps) -> ShotsOut:
    return ShotsOut(shots=[ShotOut.of(s) for s in await c.reorder_shots.execute(project_id, body.shot_ids)])
