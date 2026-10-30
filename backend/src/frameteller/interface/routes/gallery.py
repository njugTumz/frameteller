"""The gallery (ADR 0017): the creator's submit, signature, status and withdraw; the public listing, countries,
media, hearts, reports and sitemap. The admin's side is in routes/admin.py."""

from __future__ import annotations

import html
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status

from frameteller.domain import Creator, GalleryEntry, PanelStyle
from frameteller.domain.countries import COUNTRIES
from frameteller.interface.container import Container
from frameteller.interface.dto import (
    CountriesOut,
    ErrorOut,
    GalleryCardOut,
    GalleryCountryOut,
    GalleryPageOut,
    GalleryReportRequest,
    GallerySignRequest,
    GallerySubmitRequest,
    HeartOut,
    MyGalleryEntryOut,
)
from frameteller.interface.routes.deps import PROJECT_ID, Deps, ProjectId
from frameteller.interface.routes.media import serve
from frameteller.interface.visitor import browser_key, visitor_id

router = APIRouter(tags=["gallery"])

EntryId = Annotated[str, Path(pattern=PROJECT_ID)]
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorOut}}
PUBLIC_MEDIA = "public, max-age=300"  # a hidden or withdrawn entry stops loading within minutes


def suggest_country(accept_language: str) -> str | None:
    """The first region in the browser's languages ("en-KE,en;q=0.9" is KE): an approximate location to offer."""
    for tag in accept_language.split(","):
        parts = tag.split(";")[0].strip().replace("_", "-").split("-")
        region = next((x.upper() for x in parts[1:] if len(x) == 2 and x.isalpha()), None)
        if region in COUNTRIES:
            return region
    return None


def _on[T](case: T | None) -> T:
    """A gallery use case, or 404 when the gallery is not set up."""
    if case is None:
        raise HTTPException(404)
    return case


@router.post(
    "/projects/{project_id}/gallery",
    status_code=status.HTTP_202_ACCEPTED,
    responses={**NOT_FOUND, 422: {"model": ErrorOut}},
)
async def submit_to_gallery(project_id: ProjectId, body: GallerySubmitRequest, c: Deps) -> MyGalleryEntryOut:
    """Submit with consent. The gallery's copy renders and is checked in the background (job.updated
    gallery_submission); clean ones are published, doubtful ones wait for a person."""
    creator = Creator.of(body.name, body.country)
    entry = await _on(c.submit_to_gallery).execute(project_id, consent=body.consent, audio=body.audio, creator=creator)
    return MyGalleryEntryOut.of(entry)


@router.get("/projects/{project_id}/gallery", responses=NOT_FOUND)
async def my_gallery_entry(project_id: ProjectId, c: Deps) -> MyGalleryEntryOut:
    return MyGalleryEntryOut.of(await _on(c.gallery_entry).execute(project_id))


@router.patch("/projects/{project_id}/gallery", responses={**NOT_FOUND, 422: {"model": ErrorOut}})
async def sign_gallery_entry(project_id: ProjectId, body: GallerySignRequest, c: Deps) -> MyGalleryEntryOut:
    """Change or remove the name and country on the entry (empty or null removes one). A new name on a published
    entry is checked again first: the entry is `checking` until it is back (job.updated gallery_submission)."""
    creator = Creator.of(body.name, body.country)
    return MyGalleryEntryOut.of(await _on(c.sign_gallery).execute(project_id, creator))


@router.delete("/projects/{project_id}/gallery", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
async def withdraw_from_gallery(project_id: ProjectId, c: Deps) -> None:
    """Take it out of the gallery: the entry, its video and cover are deleted."""
    await _on(c.withdraw_from_gallery).execute(project_id)


@router.get("/gallery")
async def gallery(
    request: Request,
    response: Response,
    c: Deps,
    view: Annotated[Literal["featured", "newest"], Query()] = "newest",
    style: Annotated[PanelStyle | None, Query()] = None,
    country: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$", description="Only creators from this country.")] = None,
) -> GalleryPageOut:
    browse = _on(c.browse_gallery)
    entries = await browse.execute(featured=view == "featured", style=style.value if style else None, country=country)
    browser = browser_key(request)
    response.headers["Cache-Control"] = "private, no-cache"  # `hearted` is per browser
    return GalleryPageOut(
        entries=[GalleryCardOut.of(e, c.settings.app_url, browser) for e in entries],
        countries=[GalleryCountryOut(code=k, entries=n) for k, n in (await browse.countries()).items()],
    )


@router.get("/gallery/countries")
async def gallery_countries(request: Request) -> CountriesOut:
    """The countries a creator may sign with, and one to suggest from the request. Only ever a suggestion."""
    suggested = suggest_country(request.headers.get("accept-language", ""))
    return CountriesOut(codes=sorted(COUNTRIES), suggested=suggested)


async def _public(c: Container, entry_id: str) -> GalleryEntry:
    return await _on(c.browse_gallery).entry(entry_id)


@router.get("/gallery/{entry_id}/cover.webp", response_class=Response, responses=NOT_FOUND)
async def gallery_cover(entry_id: EntryId, request: Request, c: Deps) -> Response:
    entry = await _public(c, entry_id)
    assert entry.cover is not None  # public
    return serve(await c.storage.get(entry.cover), request, cache=PUBLIC_MEDIA, filename="cover.webp")


@router.get("/gallery/{entry_id}/video.mp4", response_class=Response, responses=NOT_FOUND)
async def gallery_video(entry_id: EntryId, request: Request, c: Deps) -> Response:
    entry = await _public(c, entry_id)
    assert entry.video is not None  # public
    return serve(await c.storage.get(entry.video), request, cache=PUBLIC_MEDIA, filename="frameteller.mp4")


@router.post("/gallery/{entry_id}/heart", responses=NOT_FOUND)
async def heart(entry_id: EntryId, request: Request, c: Deps) -> HeartOut:
    """One heart per browser: a second one changes nothing."""
    return HeartOut(hearts=await _on(c.heart_gallery).execute(entry_id, browser_key(request)), hearted=True)


@router.post("/gallery/{entry_id}/report", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
async def report(entry_id: EntryId, body: GalleryReportRequest, request: Request, c: Deps) -> None:
    """Flag an entry for the admin. Enough reports from different visitors hide it until the admin decides."""
    await _on(c.report_gallery).execute(entry_id, visitor_id(request), body.reason)


@router.get("/gallery/sitemap.xml", response_class=Response, include_in_schema=False)
async def sitemap(c: Deps) -> Response:
    """Every published entry's share page, for search engines (frameteller.com/robots.txt lists this)."""
    app = c.settings.app_url
    entries = await c.browse_gallery.execute() if c.browse_gallery is not None else []
    urls = [f"<url><loc>{html.escape(app)}/gallery</loc><changefreq>hourly</changefreq></url>"]
    for e in entries:
        stamp = (e.published_at or e.submitted_at).date().isoformat()
        urls.append(f"<url><loc>{html.escape(f'{app}/s/{e.share_token}')}</loc><lastmod>{stamp}</lastmod></url>")
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(urls) + "</urlset>\n"
    )
    return Response(body, media_type="application/xml", headers={"Cache-Control": "public, max-age=600"})
