from __future__ import annotations

import asyncio
import json
from pathlib import Path

from frameteller.application.errors import ProjectNotFoundError
from frameteller.domain import Project
from frameteller.infrastructure.local.serialization import project_from_dict, project_to_dict
from frameteller.infrastructure.local.storage import safe_path


class JsonFileProjectRepository:
    """ProjectRepository as one JSON document per project, written atomically."""

    def __init__(self, root: Path) -> None:
        self._root = root / "projects"
        self._lock = asyncio.Lock()

    async def get(self, project_id: str) -> Project:
        path = safe_path(self._root, f"{project_id}.json")
        try:
            text = await asyncio.to_thread(path.read_text, "utf-8")
        except FileNotFoundError:
            raise ProjectNotFoundError(project_id) from None
        return project_from_dict(json.loads(text))

    async def save(self, project: Project) -> None:
        path = safe_path(self._root, f"{project.id}.json")
        text = json.dumps(project_to_dict(project), ensure_ascii=False)
        async with self._lock:
            await asyncio.to_thread(_atomic_write, path, text)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, "utf-8")
    tmp.replace(path)
