from __future__ import annotations

import asyncio
from pathlib import Path

from frameteller.infrastructure.local.storage import safe_path


class FileVisitorQuota:
    """VisitorQuota as one line per use in quotas/<day>/<kind>/<visitor> (visitors are hashes, never raw IPs)."""

    def __init__(self, root: Path) -> None:
        self._root = root / "quotas"
        self._lock = asyncio.Lock()

    def _path(self, visitor: str, day: str, kind: str) -> Path:
        return safe_path(self._root, f"{day}/{kind}/{visitor}")

    async def used(self, visitor: str, day: str, kind: str) -> int:
        path = self._path(visitor, day, kind)

        def count() -> int:
            return len(path.read_text("utf-8").splitlines()) if path.exists() else 0

        return await asyncio.to_thread(count)

    async def add(self, visitor: str, day: str, kind: str) -> None:
        path = self._path(visitor, day, kind)

        def append() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write("1\n")

        async with self._lock:
            await asyncio.to_thread(append)
