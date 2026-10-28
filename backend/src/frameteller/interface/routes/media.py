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
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
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
    headers = {
        "ETag": etag,
        "Cache-Control": cache_control(key),
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
    }
    if request.query_params.get("download"):
        headers["Content-Disposition"] = f'attachment; filename="{key.rsplit("/", 1)[-1]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    wanted = byte_range(request.headers.get("range"), len(data))
    if wanted is None:
        return Response(data, media_type=content_type(data), headers=headers)
    start, end = wanted
    if start >= len(data):
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{len(data)}"})
    headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
    return Response(data[start : end + 1], status_code=206, media_type=content_type(data), headers=headers)


def byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """One `bytes=a-b`, `bytes=a-` or `bytes=-n` range, as the video player asks to seek. Others: whole file."""
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    first, _, last = header[len("bytes=") :].strip().partition("-")
    try:
        if not first:  # the last n bytes
            n = int(last)
            return (max(0, size - n), size - 1) if n > 0 else None
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    except ValueError:
        return None
    return (start, end) if start <= end or start >= size else None
