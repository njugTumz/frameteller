from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Request, Response, status

from frameteller.application.use_cases import MAX_DICTATION_MS
from frameteller.domain import InvalidValueError, Point, Size
from frameteller.interface.dto import (
    AnimaticRequest,
    CastApproval,
    CastReviewOut,
    CharacterMerge,
    CharacterRename,
    DictationOut,
    EditRequest,
    ErrorOut,
    JobStatusOut,
    LayerRequest,
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
    return ProjectOut.of(await c.create_project.execute(body.title, body.as_style()))


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


@router.patch("/{project_id}/cast/{character_id}")
async def rename_character(
    project_id: ProjectId, character_id: CharacterId, body: CharacterRename, c: Deps
) -> ProjectOut:
    """Rename a character. Its sheet and the cast's approval stand."""
    return ProjectOut.of(await c.rename_character.execute(project_id, character_id, body.name))


@router.delete("/{project_id}/cast/{character_id}")
async def remove_character(project_id: ProjectId, character_id: CharacterId, c: Deps) -> ProjectOut:
    """Remove a character from the cast and its shots. Shots keep their action; their panels are outdated."""
    return ProjectOut.of(await c.remove_character.execute(project_id, character_id))


@router.post("/{project_id}/cast/{character_id}/merge")
async def merge_character(
    project_id: ProjectId, character_id: CharacterId, body: CharacterMerge, c: Deps
) -> ProjectOut:
    """Merge a character into another: its shots show the other, and their panels are redrawn as drafts."""
    return ProjectOut.of((await c.merge_characters.execute(project_id, character_id, body.into)).project)


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


@router.post(
    "/{project_id}/shots/{n}/panel/layers", status_code=status.HTTP_202_ACCEPTED, responses={402: {"model": ErrorOut}}
)
async def save_layer(project_id: ProjectId, n: ShotNumber, body: LayerRequest, c: Deps) -> TicketOut:
    """Save a move, resize or delete of a selected object. A compose_panel job applies it on a clean plate."""
    shot = await c.find_shot.execute(project_id, n)
    ticket = await c.move_object.execute(
        project_id, shot.id, body.object_id, dx=body.dx, dy=body.dy, scale=body.scale, deleted=body.deleted
    )
    return TicketOut.of(ticket)


@router.post(
    "/{project_id}/exports/animatic", status_code=status.HTTP_202_ACCEPTED, responses={409: {"model": ErrorOut}}
)
async def export_animatic(project_id: ProjectId, body: AnimaticRequest, c: Deps) -> TicketOut:
    """Queue the MP4 animatic. job.updated carries progress; the project's `animatic` holds the result."""
    return TicketOut.of(await c.request_animatic.execute(project_id, subtitles=body.subtitles))


@router.get(
    "/{project_id}/exports/storyboard.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}, 409: {"model": ErrorOut}},
)
async def storyboard_pdf(project_id: ProjectId, c: Deps) -> Response:
    """The storyboard sheet: every shot with its panel, framing, action, dialogue and duration."""
    pdf = await c.storyboard_pdf.execute(project_id)
    headers = {"Content-Disposition": 'attachment; filename="storyboard.pdf"', "Cache-Control": "no-store"}
    return Response(pdf, media_type="application/pdf", headers=headers)


@router.post("/{project_id}/shots/reorder")
async def reorder_shots(project_id: ProjectId, body: ReorderRequest, c: Deps) -> ShotsOut:
    return ShotsOut(shots=[ShotOut.of(s) for s in await c.reorder_shots.execute(project_id, body.shot_ids)])


@router.delete("/{project_id}/narration")
async def delete_narration(project_id: ProjectId, c: Deps) -> ProjectOut:
    """Delete my recording: every kept narration of this project. A later animatic has no voice track."""
    return ProjectOut.of(await c.delete_narration.execute(project_id))


_WAV_BODY = {"required": True, "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}}}
_WAV_HEADER_BYTES = 44


@router.post(
    "/{project_id}/dictation",
    responses={413: {"model": ErrorOut}, 422: {"model": ErrorOut}},
    openapi_extra={"requestBody": _WAV_BODY},
)
async def dictate(project_id: ProjectId, request: Request, c: Deps) -> DictationOut:
    """Transcribe a spoken edit instruction: a WAV body, mono 16-bit at 16 or 24 kHz, at most 30 s.

    Returns the text for the user to check; nothing is edited until they send it to .../panel/edit.
    """
    wav = await request.body()
    if len(wav) <= _WAV_HEADER_BYTES or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise InvalidValueError("Send the recording as a WAV file: mono, 16-bit, 16 or 24 kHz.")
    if len(wav) > _WAV_HEADER_BYTES + 48 * MAX_DICTATION_MS:
        raise InvalidValueError(f"Keep spoken instructions under {MAX_DICTATION_MS // 1000} seconds.")
    return DictationOut(text=await c.transcribe_instruction.execute(project_id, wav))


@router.get("/{project_id}/jobs/{key}")
async def job_status(project_id: ProjectId, key: Annotated[str, Path(max_length=300)], c: Deps) -> JobStatusOut:
    """One job's status, for clients that missed its job.updated events. Keys belong to their project."""
    rest = key.partition(":")[2]
    if not rest.startswith(f"{project_id}:"):
        return JobStatusOut(key=key, status="unknown")
    found = c.jobs.status(key)
    if found is None:
        return JobStatusOut(key=key, status="unknown")
    return JobStatusOut(key=key, status=found.value, message=c.jobs.message(key))
