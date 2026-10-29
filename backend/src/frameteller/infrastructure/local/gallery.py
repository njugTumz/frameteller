"""The gallery document (ADR 0017): JSON for both adapters, and the file-backed GalleryRepository."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from frameteller.domain import EntryStatus, Gallery, GalleryEntry, MediaRef, Report


def _ref(r: MediaRef | None) -> str | None:
    return r.key if r else None


def _unref(k: str | None) -> MediaRef | None:
    return MediaRef(k) if k else None


def gallery_to_dict(g: Gallery) -> dict[str, Any]:
    return {
        "entries": [
            {
                "id": e.id,
                "project_id": e.project_id,
                "share_token": e.share_token,
                "title": e.title,
                "style": e.style,
                "episodes": e.episodes,
                "shots": e.shots,
                "audio": e.audio,
                "submitted_at": e.submitted_at.isoformat(),
                "status": e.status.value,
                "featured": e.featured,
                "cover": _ref(e.cover),
                "video": _ref(e.video),
                "duration_ms": e.duration_ms,
                "note": e.note,
                "reviewed_by": e.reviewed_by,
                "published_at": e.published_at.isoformat() if e.published_at else None,
                "hearts": sorted(e.hearts),
                "reports": [{"visitor": r.visitor, "reason": r.reason, "at": r.at.isoformat()} for r in e.reports],
            }
            for e in g.entries.values()
        ]
    }


def gallery_from_dict(d: dict[str, Any]) -> Gallery:
    entries = {}
    for e in d.get("entries", []):
        entries[e["id"]] = GalleryEntry(
            e["id"],
            e["project_id"],
            e["share_token"],
            e["title"],
            e["style"],
            e["episodes"],
            e["shots"],
            e["audio"],
            datetime.fromisoformat(e["submitted_at"]),
            EntryStatus(e["status"]),
            e.get("featured", False),
            _unref(e.get("cover")),
            _unref(e.get("video")),
            e.get("duration_ms", 0),
            e.get("note", ""),
            e.get("reviewed_by", ""),
            datetime.fromisoformat(e["published_at"]) if e.get("published_at") else None,
            set(e.get("hearts", [])),
            [Report(r["visitor"], r["reason"], datetime.fromisoformat(r["at"])) for r in e.get("reports", [])],
        )
    return Gallery(entries)


class FileGalleryRepository:
    """GalleryRepository as one JSON file (gallery.json), written atomically under a lock (one container)."""

    def __init__(self, root: Path) -> None:
        self._path = root / "gallery.json"
        self._lock = asyncio.Lock()

    async def get(self) -> Gallery:
        try:
            text = await asyncio.to_thread(self._path.read_text, "utf-8")
        except FileNotFoundError:
            return Gallery()
        return gallery_from_dict(json.loads(text))

    async def update[T](self, change: Callable[[Gallery], T]) -> T:
        async with self._lock:
            gallery = await self.get()
            result = change(gallery)
            await asyncio.to_thread(self._write, json.dumps(gallery_to_dict(gallery), ensure_ascii=False))
            return result

    def _write(self, text: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(text, "utf-8")
        tmp.replace(self._path)
