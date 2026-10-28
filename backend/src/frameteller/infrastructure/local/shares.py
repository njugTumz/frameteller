from __future__ import annotations

import asyncio
from pathlib import Path

from frameteller.infrastructure.local.storage import safe_path


class FileShareIndex:
    """ShareIndex as one small file per token, holding the project id."""

    def __init__(self, root: Path) -> None:
        self._root = root / "shares"

    async def put(self, token: str, project_id: str) -> None:
        path = safe_path(self._root, token)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(project_id, "utf-8")

        await asyncio.to_thread(write)

    async def find(self, token: str) -> str | None:
        try:
            return await asyncio.to_thread(safe_path(self._root, token).read_text, "utf-8")
        except (FileNotFoundError, ValueError):
            return None

    async def delete(self, token: str) -> None:
        await asyncio.to_thread(safe_path(self._root, token).unlink, missing_ok=True)
