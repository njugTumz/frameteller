from __future__ import annotations

import asyncio
import re
from pathlib import Path

from frameteller.domain import MediaRef

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.:-]*$")


def safe_path(root: Path, key: str) -> Path:
    """Resolve a storage key under root, refusing absolute paths and traversal."""
    if not _SAFE_KEY.match(key) or ".." in key.split("/"):
        raise ValueError(f"unsafe storage key {key!r}")
    path = (root / key).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"unsafe storage key {key!r}")
    return path


class LocalFileMediaStorage:
    """MediaStoragePort on the local disk. Content types are not kept; keys and callers know them."""

    def __init__(self, root: Path) -> None:
        self._root = root / "media"

    async def put(self, key: str, data: bytes, content_type: str) -> MediaRef:
        path = safe_path(self._root, key)
        await asyncio.to_thread(_write, path, data)
        return MediaRef(key)

    async def get(self, ref: MediaRef) -> bytes:
        return await asyncio.to_thread(safe_path(self._root, ref.key).read_bytes)


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
