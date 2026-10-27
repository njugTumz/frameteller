from __future__ import annotations

import hashlib

from fastapi import APIRouter, Request, Response

from frameteller.domain import InvalidValueError, MediaRef
from frameteller.interface.errors import error_response
from frameteller.interface.routes.deps import Deps

router = APIRouter(tags=["media"])

_SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"%PDF", "application/pdf"),
]


def content_type(data: bytes) -> str:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp":
        return "video/mp4"
    return next((t for sig, t in _SIGNATURES if data.startswith(sig)), "application/octet-stream")


def cache_control(key: str) -> str:
    # Panel revisions (and their masks) get new keys on every render, so they never change in place.
    # Reference sheets keep their key when redrawn, so browsers revalidate them with the ETag.
    immutable = "/panels/" in key and any(part[:1] == "r" and part[1:].isdigit() for part in key.split("/"))
    return "private, max-age=31536000, immutable" if immutable else "private, no-cache"


@router.get("/media/{key:path}", response_class=Response, responses={200: {"content": {"image/webp": {}}}})
async def get_media(key: str, request: Request, c: Deps) -> Response:
    """Stream a stored file. Keys come from the project's *_url fields."""
    if not key.startswith("projects/"):
        return error_response(404, "media_not_found", "No such file.")
    try:
        data = await c.storage.get(MediaRef(key))
    except (FileNotFoundError, KeyError, ValueError, InvalidValueError):
        return error_response(404, "media_not_found", "No such file.")
    etag = '"' + hashlib.sha256(data).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": cache_control(key), "X-Content-Type-Options": "nosniff"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(data, media_type=content_type(data), headers=headers)
