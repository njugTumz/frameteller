"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from frameteller.infrastructure.config import Settings
from frameteller.interface import errors
from frameteller.interface.container import Container, build_container
from frameteller.interface.middleware import BodyLimitMiddleware, RateLimitMiddleware, RequestContextMiddleware
from frameteller.interface.routes import health, media, projects, session

DESCRIPTION = """Frameteller turns spoken stories into storyboards.

REST covers projects, cast approval, panels, edits and selection. Live narration and every
asynchronous result (shots, cast proposals, job progress) travel over the WebSocket
`/ws/projects/{project_id}/session`, documented in `docs/api-events.md`."""


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """With settings, real adapters are built at startup. With a container (tests), it is used as is.

    With neither, the app still describes itself: scripts/export_openapi.py uses that.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if getattr(app.state, "container", None) is None and settings is not None:
            app.state.container = build_container(settings)
        yield
        current: Container | None = getattr(app.state, "container", None)
        if current is not None:
            await current.jobs.join()  # let queued renders finish on a graceful shutdown

    app = FastAPI(title="Frameteller API", version="0.1.0", description=DESCRIPTION, lifespan=lifespan)
    if container is not None:
        app.state.container = container
    errors.install(app)
    for router in (projects.router, media.router, health.router, session.router):
        app.include_router(router)

    config = settings or (container.settings if container else None)
    # Added inside out: the last one added runs first.
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        per_minute=config.rate_limit_per_minute if config else 120,
        costly_per_minute=config.rate_limit_costly_per_minute if config else 20,
    )
    if config and config.origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )
    app.add_middleware(RequestContextMiddleware)
    return app
