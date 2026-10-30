"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from frameteller.infrastructure.config import Settings
from frameteller.interface import errors
from frameteller.interface.container import Container, build_container
from frameteller.interface.judge import JudgeMiddleware
from frameteller.interface.middleware import (
    BodyLimitMiddleware,
    PauseMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
)
from frameteller.interface.routes import (
    admin,
    gallery,
    health,
    internal,
    judge,
    media,
    projects,
    session,
    shares,
    voices,
)
from frameteller.interface.visitor import VISITOR_HEADER

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
            if current.incidents is not None:
                await current.incidents.flush()  # today's model health, written at most every 15 s

    app = FastAPI(title="Frameteller API", version="0.1.0", description=DESCRIPTION, lifespan=lifespan)
    if container is not None:
        app.state.container = container
    errors.install(app)
    routers = (projects, shares, media, health, session, internal, voices, judge, admin, gallery)
    for router in (r.router for r in routers):
        app.include_router(router)

    config = settings or (container.settings if container else None)
    # Added inside out: the last one added runs first.
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(PauseMiddleware, paused=bool(config and config.demo_paused))
    app.add_middleware(
        RateLimitMiddleware,
        per_minute=config.rate_limit_per_minute if config else 120,
        costly_per_minute=config.rate_limit_costly_per_minute if config else 20,
    )
    judge_token = config.judge_token if config else None
    # Sets the lane (public or judge) for everything inside it: limits, budgets, queues.
    app.add_middleware(JudgeMiddleware, token=lambda: judge_token.get_secret_value() if judge_token else None)
    if config and config.origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-Request-ID", "Authorization", VISITOR_HEADER],
            expose_headers=["X-Request-ID"],
            allow_credentials=True,  # the judge cookie; origins are an explicit list, never "*"
        )
    app.add_middleware(RequestContextMiddleware)
    return app
