"""POST /judge: trade the private judge link's token for a signed cookie. DELETE /judge: leave the judge lane."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from frameteller.interface.dto import ErrorOut
from frameteller.interface.errors import error_response
from frameteller.interface.judge import COOKIE, issue, token_matches
from frameteller.interface.routes.deps import Deps

router = APIRouter(tags=["judge"])


class JudgeIn(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class JudgeOut(BaseModel):
    judge: bool
    until: str | None = Field(description="When the pass runs out (ISO 8601, UTC).")


def _same_site(secure: bool) -> Literal["none", "lax"]:
    # Cross-site on staging (azurestaticapps.net -> azurecontainerapps.io), same-site in production.
    return "none" if secure else "lax"


@router.post("/judge", response_model=JudgeOut, responses={403: {"model": ErrorOut}, 404: {"model": ErrorOut}})
async def enter(body: JudgeIn, response: Response, c: Deps) -> JudgeOut | Response:
    """Judges skip the per-visitor caps and the waiting room, and draw from a reserved daily budget."""
    token = c.settings.judge_token
    if token is None:
        return error_response(404, "not_found", "There is no judge access on this studio.")
    if not token_matches(token.get_secret_value(), body.token):
        return error_response(403, "forbidden", "That judge link is not valid any more. Ask the team for a new one.")
    value, expires = issue(token.get_secret_value(), c.settings.judge_pass_days)
    secure = c.settings.app_env != "local"
    response.set_cookie(
        COOKIE,
        value,
        max_age=expires - int(datetime.now(UTC).timestamp()),
        httponly=True,
        secure=secure,
        samesite=_same_site(secure),
    )
    until = datetime.fromtimestamp(expires, UTC).isoformat(timespec="seconds")
    return JudgeOut(judge=True, until=until)


@router.delete("/judge", status_code=status.HTTP_204_NO_CONTENT)
async def leave(response: Response, c: Deps) -> None:
    secure = c.settings.app_env != "local"
    response.delete_cookie(COOKIE, httponly=True, secure=secure, samesite=_same_site(secure))
