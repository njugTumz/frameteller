"""The public gallery (ADR 0017): storyboards their creators chose to show, checked before anyone sees them.

An entry starts as `checking` while its video renders and the moderation review runs. A clean review publishes
it; a doubtful one leaves it `pending` for the admin. Visitors heart an entry once per browser and can report it;
enough reports hide it until the admin looks. The creator can withdraw it at any time, which deletes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal

from frameteller.domain.errors import InvalidValueError
from frameteller.domain.media import MediaRef

GalleryAudio = Literal["mine", "voice", "none"]  # the creator's voice, the Ava voice instead, or silent
REPORTS_TO_HIDE = 3  # distinct visitors reporting a published entry hide it until the admin decides
MAX_REPORT_CHARS = 300


class EntryStatus(StrEnum):
    CHECKING = "checking"  # the video is rendering and the moderation review is running
    PUBLISHED = "published"
    PENDING = "pending"  # the review was unsure, or could not run: the admin decides
    HIDDEN = "hidden"  # the admin hid it, or reports did
    FAILED = "failed"  # the video could not be made


@dataclass(frozen=True, slots=True)
class Report:
    visitor: str  # a hash of IP and browser id, never either one
    reason: str
    at: datetime


@dataclass(slots=True)
class GalleryEntry:
    id: str
    project_id: str
    share_token: str
    title: str
    style: str
    episodes: int
    shots: int
    audio: GalleryAudio
    submitted_at: datetime
    status: EntryStatus = EntryStatus.CHECKING
    featured: bool = False
    cover: MediaRef | None = None  # a copy of the first panel: later edits to the project never change it
    video: MediaRef | None = None
    duration_ms: int = 0
    note: str = ""  # why it is pending, hidden or failed (for the admin and the creator)
    reviewed_by: str = ""  # the model that ran the moderation review
    published_at: datetime | None = None
    hearts: set[str] = field(default_factory=set)  # visitor hashes
    reports: list[Report] = field(default_factory=list)

    @property
    def public(self) -> bool:
        return self.status is EntryStatus.PUBLISHED and self.video is not None and self.cover is not None

    def ready(self, cover: MediaRef, video: MediaRef, duration_ms: int) -> None:
        self.cover, self.video, self.duration_ms = cover, video, duration_ms

    def publish(self, at: datetime, reviewed_by: str = "") -> None:
        if self.video is None or self.cover is None:
            raise InvalidValueError("an entry needs its video and cover before it is published")
        self.status, self.note = EntryStatus.PUBLISHED, ""
        self.reviewed_by = reviewed_by or self.reviewed_by
        self.published_at = self.published_at or at

    def hold(self, note: str, reviewed_by: str = "") -> None:
        """Leave it for the admin."""
        self.status, self.note = EntryStatus.PENDING, note
        self.reviewed_by = reviewed_by or self.reviewed_by

    def hide(self, note: str) -> None:
        self.status, self.note, self.featured = EntryStatus.HIDDEN, note, False

    def fail(self, note: str) -> None:
        self.status, self.note = EntryStatus.FAILED, note

    def feature(self, on: bool) -> None:
        if on and self.status is not EntryStatus.PUBLISHED:
            raise InvalidValueError("only a published entry can be featured")
        self.featured = on

    def heart(self, visitor: str) -> bool:
        """One heart per browser. True when this one is new."""
        if visitor in self.hearts:
            return False
        self.hearts.add(visitor)
        return True

    def report(self, visitor: str, reason: str, at: datetime) -> bool:
        """One report per visitor. True when the reports just hid the entry."""
        if any(r.visitor == visitor for r in self.reports):
            return False
        self.reports.append(Report(visitor, reason.strip()[:MAX_REPORT_CHARS], at))
        if self.status is EntryStatus.PUBLISHED and len(self.reports) >= REPORTS_TO_HIDE:
            self.hide(f"Hidden after {len(self.reports)} reports.")
            return True
        return False


@dataclass(slots=True)
class Gallery:
    """Every entry, at most one per project. Small enough to keep as one document."""

    entries: dict[str, GalleryEntry] = field(default_factory=dict)

    def find(self, entry_id: str) -> GalleryEntry | None:
        return self.entries.get(entry_id)

    def of_project(self, project_id: str) -> GalleryEntry | None:
        return next((e for e in self.entries.values() if e.project_id == project_id), None)

    def submit(self, entry: GalleryEntry) -> GalleryEntry | None:
        """Add an entry, replacing the project's earlier one (returned, so its media can be deleted)."""
        previous = self.of_project(entry.project_id)
        if previous is not None:
            del self.entries[previous.id]
        self.entries[entry.id] = entry
        return previous

    def remove(self, entry_id: str) -> GalleryEntry | None:
        return self.entries.pop(entry_id, None)

    def published(self, *, style: str | None = None, featured: bool = False) -> list[GalleryEntry]:
        """Public entries: featured first then newest, or newest only."""
        shown = [e for e in self.entries.values() if e.public and (style is None or e.style == style)]
        if featured:
            shown = [e for e in shown if e.featured]
        return sorted(shown, key=lambda e: e.published_at or e.submitted_at, reverse=True)
