"""FastAPI dependencies: the container from app state, and the project id in every log line."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Path
from starlette.requests import HTTPConnection

from frameteller.infrastructure.observability import project_id_var
from frameteller.interface.container import Container

PROJECT_ID = r"^[A-Za-z0-9_-]{1,64}$"


def get_container(connection: HTTPConnection) -> Container:
    container: Container = connection.app.state.container
    return container


async def project_scope(project_id: Annotated[str, Path(pattern=PROJECT_ID)]) -> str:
    """Async on purpose: it runs in the request's context, so the log context variable sticks."""
    project_id_var.set(project_id)
    return project_id


Deps = Annotated[Container, Depends(get_container)]
ProjectId = Annotated[str, Depends(project_scope)]
