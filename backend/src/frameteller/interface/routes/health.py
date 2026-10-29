from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from frameteller.interface.dto import StudioStatusOut
from frameteller.interface.routes.deps import Deps

router = APIRouter(tags=["health"])
log = logging.getLogger("frameteller.health")

CHECK_TIMEOUT_S = 2.0


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """The process is up."""
    return {"status": "ok"}


@router.get("/readyz", responses={503: {"description": "A dependency is not ready"}})
async def readyz(c: Deps) -> JSONResponse:
    """Settings loaded (the container exists) and storage writable. Never calls Meta: probes must be free."""
    results = {"settings": "ok"}
    for name, check in c.readiness.items():
        try:
            await asyncio.wait_for(check(), CHECK_TIMEOUT_S)
            results[name] = "ok"
        except Exception as exc:
            log.warning("readiness check failed", extra={"check": name, "error": type(exc).__name__})
            results[name] = "failed"
    ready = all(v == "ok" for v in results.values())
    return JSONResponse({"status": "ready" if ready else "not_ready", "checks": results}, 200 if ready else 503)


@router.get("/status")
async def studio_status(c: Deps) -> StudioStatusOut:
    """Paused (kill switch) or full for today (global spend cap), and the public-demo limits."""
    return StudioStatusOut.of(await c.studio_status.execute())
