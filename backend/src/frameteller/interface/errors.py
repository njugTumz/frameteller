"""Map application and domain errors to HTTP responses with user-facing messages. Nothing internal leaks."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from frameteller.application.errors import (
    ApplicationError,
    BudgetExceededError,
    ModelError,
    ModelRateLimitedError,
    ModelTimeoutError,
    NothingToSegmentError,
    ProjectNotFoundError,
    ShareNotFoundError,
)
from frameteller.domain import (
    DomainError,
    InvalidValueError,
    UnknownCharacterError,
    UnknownObjectError,
    UnknownShotError,
)

log = logging.getLogger("frameteller.api")

# First match wins, so subclasses come before their bases.
_STATUS: list[tuple[type[Exception], int, str]] = [
    (ProjectNotFoundError, 404, "project_not_found"),
    (ShareNotFoundError, 404, "share_not_found"),
    (UnknownShotError, 404, "shot_not_found"),
    (UnknownCharacterError, 404, "character_not_found"),
    (UnknownObjectError, 404, "object_not_found"),
    (BudgetExceededError, 402, "budget_exceeded"),
    (NothingToSegmentError, 422, "nothing_to_select"),
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


async def handle(request: Request, exc: Exception) -> JSONResponse:
    status, code, message = describe(exc)
    if status >= 500:
        log.warning("request failed", extra={"code": code, "error": type(exc).__name__})
    headers = {"Retry-After": "10"} if status == 503 else None
    return error_response(status, code, message, headers)


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled error", exc_info=exc)
    return error_response(500, "error", ApplicationError.user_message)


def install(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, handle)
    app.add_exception_handler(ApplicationError, handle)
    app.add_exception_handler(Exception, handle_unexpected)  # JSON, never a stack trace
