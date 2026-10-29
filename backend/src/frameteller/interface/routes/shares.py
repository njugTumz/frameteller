"""Read-only share links (/s/{token}) and what the share page loads. Nothing here reveals the project id.

A link is unlisted unless its owner makes it public: every response then carries `X-Robots-Tag: noindex` and
the stub page a robots meta tag, so search engines leave it out. Crawlers that fetch link previews (X) still
read the tags; noindex only keeps the page out of search results.
"""

from __future__ import annotations

import html
from typing import Annotated, Any

from fastapi import APIRouter, Path, Request, Response, status
from fastapi.responses import HTMLResponse

from frameteller.application.errors import ShareNotFoundError
from frameteller.domain import PanelStatus, Project
from frameteller.interface.dto import ErrorOut, SharedProjectOut, ShareOut, ShareRequest
from frameteller.interface.errors import error_response
from frameteller.interface.routes.deps import PROJECT_ID, Deps, ProjectId
from frameteller.interface.routes.media import serve

router = APIRouter(tags=["shares"])

Token = Annotated[str, Path(pattern=PROJECT_ID)]
SHARED = "public, max-age=60"  # revoking takes effect within a minute
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorOut}}
NOINDEX = "noindex, nofollow"


def links(request: Request, token: str, app_url: str, public: bool) -> ShareOut:
    api = str(request.base_url).rstrip("/")
    return ShareOut(token=token, public=public, url=f"{api}/s/{token}", page_url=f"{app_url}/s/{token}")


def robots[R: Response](response: R, project: Project) -> R:
    if not project.share_public:
        response.headers["X-Robots-Tag"] = NOINDEX
    return response


@router.post("/projects/{project_id}/share", responses=NOT_FOUND)
async def share_project(project_id: ProjectId, request: Request, c: Deps, body: ShareRequest | None = None) -> ShareOut:
    """Turn on the read-only link, unlisted unless `public`. Calling it again keeps the link and sets `public`."""
    public = body.public if body else False
    token = await c.share_project.execute(project_id, public=public)
    return links(request, token, c.settings.app_url, public)


@router.delete("/projects/{project_id}/share", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
async def revoke_share(project_id: ProjectId, c: Deps) -> None:
    """Turn the link off. Pages already open stop loading within a minute."""
    await c.revoke_share.execute(project_id)


@router.get("/shares/{token}", responses=NOT_FOUND)
async def get_share(token: Token, response: Response, c: Deps) -> SharedProjectOut:
    project = await c.open_share.execute(token)
    robots(response, project)
    return SharedProjectOut.of(project, token)


@router.get("/shares/{token}/panels/{n}", response_class=Response, responses=NOT_FOUND)
async def shared_panel(token: Token, n: Annotated[int, Path(ge=1, le=10_000)], request: Request, c: Deps) -> Response:
    project = await c.open_share.execute(token)
    shot = next((s for s in project.shots if s.number == n), None)
    panel = project.panels.get(shot.id) if shot else None
    if panel is None or panel.status is not PanelStatus.READY or panel.shown_image is None:
        return error_response(404, "media_not_found", "No such file.")
    return robots(
        serve(await c.storage.get(panel.shown_image), request, cache=SHARED, filename=f"shot-{n}.webp"), project
    )


@router.get("/shares/{token}/animatic", response_class=Response, responses=NOT_FOUND)
async def shared_animatic(token: Token, request: Request, c: Deps) -> Response:
    project = await c.open_share.execute(token)
    if project.animatic is None:
        return error_response(404, "media_not_found", "No animatic yet.")
    return robots(
        serve(await c.storage.get(project.animatic.video), request, cache=SHARED, filename="animatic.mp4"), project
    )


@router.get("/shares/{token}/og.png", response_class=Response, responses=NOT_FOUND)
async def share_image(token: Token, request: Request, c: Deps) -> Response:
    """The link preview: the title over the first six panels, 1200x630."""
    project = await c.open_share.execute(token)
    return robots(
        serve(await c.share_preview.execute(token), request, cache=SHARED, filename="storyboard.png"), project
    )


@router.get("/s/{token}", response_class=HTMLResponse, include_in_schema=False)
async def share_stub(token: Token, request: Request, c: Deps) -> HTMLResponse:
    """The link people post. Crawlers read the preview tags; browsers move on to the share page at once."""
    page = f"{c.settings.app_url}/s/{token}"
    try:
        project = await c.open_share.execute(token)
    except ShareNotFoundError:  # the share page explains that the link was turned off
        return HTMLResponse(
            _redirect(page, "Frameteller", f'<meta name="robots" content="{NOINDEX}">\n'),
            status_code=404,
            headers={"Cache-Control": SHARED, "X-Robots-Tag": NOINDEX},
        )
    image = f"{str(request.base_url).rstrip('/')}/shares/{token}/og.png"
    title = html.escape(project.title or "A storyboard")
    description = html.escape(preview_description(len(project.shots), project.animatic is not None))
    listed = "" if project.share_public else f'<meta name="robots" content="{NOINDEX}">\n'
    tags = f"""{listed}<meta name="description" content="{description}">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{html.escape(image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{html.escape(page)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{html.escape(image)}">
"""
    return robots(HTMLResponse(_redirect(page, title, tags), headers={"Cache-Control": SHARED}), project)


def preview_description(shots: int, animatic: bool) -> str:
    """e.g. "A 6-shot storyboard and animatic, told out loud with Frameteller." """
    what = f"A {shots}-shot storyboard" if shots else "A storyboard"
    return f"{what}{' and animatic' if animatic else ''}, told out loud with Frameteller."


def _redirect(page: str, title: str, tags: str) -> str:
    """A page with no script: CSP-safe. The refresh moves browsers on; crawlers stop at the tags."""
    target = html.escape(page)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{title}</title>
{tags}<meta http-equiv="refresh" content="0;url={target}">
</head><body><p><a href="{target}">Open the storyboard</a></p></body></html>
"""
