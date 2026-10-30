"""Map application and domain errors to HTTP responses with user-facing messages. Nothing internal leaks."""

from __future__ import annotations

import logging
import re

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from frameteller.application.errors import (
    ApplicationError,
    BudgetExceededError,
    GalleryEntryNotFoundError,
    GallerySubmissionError,
    LimitReachedError,
    ModelError,
    ModelRateLimitedError,
    ModelTimeoutError,
    NothingToSegmentError,
    ProjectNotFoundError,
    RefusedUnchangedError,
    ScriptError,
    ShareNotFoundError,
    StudioFullError,
)
from frameteller.application.incidents import RetryRefusedError, clean
from frameteller.domain import (
    DomainError,
    InvalidValueError,
    UnknownCharacterError,
    UnknownObjectError,
    UnknownShotError,
    UnknownTurnError,
)
from frameteller.infrastructure.observability import project_id_var

log = logging.getLogger("frameteller.api")

# First match wins, so subclasses come before their bases.
_STATUS: list[tuple[type[Exception], int, str]] = [
    (ProjectNotFoundError, 404, "project_not_found"),
    (ShareNotFoundError, 404, "share_not_found"),
    (GalleryEntryNotFoundError, 404, "gallery_entry_not_found"),
    (GallerySubmissionError, 422, "gallery_submission"),
    (RetryRefusedError, 409, "retry_refused"),
    (RefusedUnchangedError, 409, "edit_first"),
    (UnknownShotError, 404, "shot_not_found"),
    (UnknownTurnError, 404, "beat_not_found"),
    (UnknownCharacterError, 404, "character_not_found"),
    (UnknownObjectError, 404, "object_not_found"),
    (StudioFullError, 503, "studio_full"),  # before its base: the global cap, not this project's
    (BudgetExceededError, 402, "budget_exceeded"),
    (LimitReachedError, 429, "limit_reached"),
    (NothingToSegmentError, 422, "nothing_to_select"),
    (ScriptError, 422, "invalid_script"),
    (ModelRateLimitedError, 503, "model_busy"),
    (ModelTimeoutError, 504, "model_timeout"),
    (ModelError, 502, "model_error"),
    (InvalidValueError, 422, "invalid_value"),
    (DomainError, 409, "conflict"),  # a story rule: cast not approved, panel not ready, bad order...
    (ApplicationError, 500, "error"),
]


def describe(exc: Exception) -> tuple[int, str, str]:
    for kind, status, code in _STATUS:
        if isinstance(exc, kind):
            # Application errors carry a user-facing message; domain errors name the broken rule.
            message = exc.user_message if isinstance(exc, ApplicationError) else str(exc)
            return status, code, message
    return 500, "error", ApplicationError.user_message


def error_response(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


_NOT_RECORDED = {401, 403, 404}  # sign-in and lookups: noise, not errors
_PROJECT = re.compile(r"^/projects/([A-Za-z0-9_-]{1,64})")
_PATHS = (  # which part of the studio a request is about, first match wins
    ("/session", "voice"),
    ("/dictation", "voice"),
    ("/panel/select", "sam"),
    ("/review", "supervisor"),
    ("/panel", "image"),
    ("/cast", "image"),
    ("/exports", "export"),
    ("/gallery", "gallery"),
    ("/voices", "tts"),
    ("/read", "tts"),
)


def component_of(path: str) -> str:
    return next((c for marker, c in _PATHS if marker in path), "api")


async def record(request: Request, status: int, code: str, message: str) -> None:
    """Note an HTTP error for the admin's Errors tab. Never raises."""
    container = getattr(request.app.state, "container", None)
    desk = getattr(container, "incidents", None)
    if desk is None or status in _NOT_RECORDED:
        return
    path = request.url.path
    found = _PROJECT.match(path)
    project = project_id_var.get() or (found.group(1) if found else None)
    await desk.error(component_of(path), code, f"{request.method} {path}: {message}", project_id=project)


async def handle(request: Request, exc: Exception) -> JSONResponse:
    status, code, message = describe(exc)
    if status >= 500:
        log.warning("request failed", extra={"code": code, "error": type(exc).__name__})
    if not isinstance(exc, ModelError):  # a model that gave up is recorded where it gave up, with its component
        # Our own messages in full; a broken story rule may quote the user's words, so only its first 80 characters.
        await record(request, status, code, message if isinstance(exc, ApplicationError) else clean(message, 80))
    headers = {"Retry-After": "10"} if status == 503 else None
    return error_response(status, code, message, headers)


async def handle_invalid(request: Request, exc: Exception) -> Response:
    """FastAPI's own 422 for a request that doesn't match its schema, recorded with where it went wrong."""
    assert isinstance(exc, RequestValidationError)
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(part) for part in first.get("loc", ()))
    await record(request, 422, "invalid_request", clean(f"{where}: {first.get('msg', 'invalid')}", 80))
    return await request_validation_exception_handler(request, exc)


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled error", exc_info=exc)
    await record(request, 500, "error", f"Unexpected {type(exc).__name__}.")
    return error_response(500, "error", ApplicationError.user_message)


def install(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, handle)
    app.add_exception_handler(ApplicationError, handle)
    app.add_exception_handler(RequestValidationError, handle_invalid)
    app.add_exception_handler(Exception, handle_unexpected)  # JSON, never a stack trace
