"""Operator routes, not part of the studio's API: the warm-up script's Glimmer lease (ADR 0013)."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from frameteller.interface.container import Container
from frameteller.interface.routes.deps import Deps

router = APIRouter(tags=["internal"], include_in_schema=False)


class LeaseIn(BaseModel):
    minutes: int = Field(ge=1, le=30, description="How long Glimmer counts as warm from now.")


class LeaseOut(BaseModel):
    warm_until: str | None


def _authorised(c: Container, authorization: str | None) -> None:
    """The bearer is the Glimmer endpoint token: only whoever can call Glimmer can say it is warm."""
    key = c.settings.glimmer_api_key
    if c.glimmer_lease is None or key is None:
        raise HTTPException(404)  # Glimmer is not gated here: there is nothing to lease
    expected = f"Bearer {key.get_secret_value()}"
    if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(401)


@router.post("/internal/glimmer/lease")
async def grant_lease(body: LeaseIn, c: Deps, authorization: Annotated[str | None, Header()] = None) -> LeaseOut:
    _authorised(c, authorization)
    assert c.glimmer_lease is not None
    until = await c.glimmer_lease.grant(body.minutes)
    return LeaseOut(warm_until=until.isoformat(timespec="seconds"))


@router.delete("/internal/glimmer/lease")
async def revoke_lease(c: Deps, authorization: Annotated[str | None, Header()] = None) -> LeaseOut:
    _authorised(c, authorization)
    assert c.glimmer_lease is not None
    await c.glimmer_lease.revoke()
    return LeaseOut(warm_until=None)
