"""The public gallery (ADR 0017): storyboards their creators chose to show, checked before anyone sees them.

An entry starts as `checking` while its video renders and the moderation review runs. A clean review publishes
it; a doubtful one leaves it `pending` for the admin. Visitors heart an entry once per browser and can report it;
enough reports hide it until the admin looks. The creator can withdraw it at any time, which deletes it.

A creator may sign an entry with a display name and a country, both optional and editable later. A new name on a
published entry is checked again before it shows; one with contact details never publishes by itself.

Some names are reserved for us and our partners ("Frameteller team", "Meta", ...). Matching ignores case, spaces and
punctuation, so "frame-teller TEAM" is reserved too. A creator who signs with one is always held for the admin,
without asking a model, so the same name never passes once and fails once. Only the admin console can publish or
sign an entry with a reserved name, which marks it official (an "Official" badge).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal

from frameteller.domain.countries import COUNTRIES
from frameteller.domain.errors import InvalidValueError
from frameteller.domain.media import MediaRef

GalleryAudio = Literal["mine", "voice", "none"]  # the creator's voice, the Ava voice instead, or silent
REPORTS_TO_HIDE = 3  # distinct visitors reporting a published entry hide it until the admin decides
MAX_REPORT_CHARS = 300
MAX_NAME_CHARS = 40

# Contact details in a display name: an email, a link or domain, a social handle, or a phone number.
_EMAIL = re.compile(r"\S+@\S+\.\S+")
_LINK = re.compile(r"https?://|www\.|\b[\w-]+\.(com|net|org|io|co|me|tv|gg|app|dev|ly|info|biz|xyz)\b", re.I)
_HANDLE = re.compile(r"(^|\s)@\w{2,}")
_PHONE = re.compile(r"\d[\d\s().+-]{5,}\d")

RESERVED_NAMES = ("Frameteller", "Frameteller team", "Frameteller official", "Meta", "Muse", "Cerebral Valley")
RESERVED_NOTE = "GAL-08: The name is reserved for official entries. Only the admin can publish it."


def _bare(name: str) -> str:
    """A name without case, spaces or punctuation: "Frame-teller  TEAM!" is "frametellerteam"."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", name).casefold() if ch.isalnum())


_RESERVED = frozenset(_bare(n) for n in RESERVED_NAMES)


@dataclass(frozen=True, slots=True)
class Creator:
    """Who made an entry, as they chose to sign it: a display name (any nickname) and a country, both optional."""

    name: str = ""
    country: str = ""  # ISO 3166-1 alpha-2, or empty
    official: bool = False  # signed or published from the admin console: a reserved name may show

    @classmethod
    def of(cls, name: str | None, country: str | None) -> Creator:
        """Validated: the name trimmed to one line of at most 40 characters, the country a known code."""
        clean = " ".join((name or "").split())
        if any(unicodedata.category(ch) in ("Cc", "Cf") for ch in clean):
            raise InvalidValueError("Your name can't contain control characters.")
        if len(clean) > MAX_NAME_CHARS:
            raise InvalidValueError(f"Your name can be at most {MAX_NAME_CHARS} characters.")
        code = (country or "").strip().upper()
        if code and code not in COUNTRIES:
            raise InvalidValueError("Choose a country from the list, or leave it empty.")
        return cls(clean, code)

    @property
    def anonymous(self) -> bool:
        return not self.name and not self.country

    @property
    def reserved(self) -> bool:
        """The name is one of ours or a partner's (RESERVED_NAMES), however it is spelled or spaced."""
        return bool(self.name) and _bare(self.name) in _RESERVED

    @property
    def held(self) -> bool:
        """A reserved name the admin has not signed or published: never published without a person."""
        return self.reserved and not self.official

    def as_official(self) -> Creator:
        """The admin signed or published it: official when the name is reserved (no badge on any other name)."""
        return Creator(self.name, self.country, official=self.reserved)

    def contact_details(self) -> str | None:
        """Why the name can't publish without a person looking: it carries contact details. None when clean."""
        if _EMAIL.search(self.name):
            return "The name has an email address."
        if _LINK.search(self.name):
            return "The name has a link."
        if _HANDLE.search(self.name):
            return "The name has a social handle."
        if _PHONE.search(self.name):
            return "The name has a phone number."
        return None


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
    creator: Creator = field(default_factory=Creator)
    checks: int = 0  # moderation reviews run again after the creator renamed it

    def sign(self, creator: Creator) -> bool:
        """The creator changes or removes their name or country. True when the entry must be checked again.

        Removing details, or changing only the country (from a fixed list), shows at once. A new name on a
        published entry takes it out of the gallery until the check passes; a pending, hidden or failed entry
        keeps its status. While the first check runs, nothing can change, so the check sees the final name.
        """
        if self.status is EntryStatus.CHECKING:
            raise InvalidValueError("Your entry is being checked. You can edit it in a minute.")
        renamed = bool(creator.name) and creator.name != self.creator.name
        self.creator = creator
        if not (renamed or creator.held) or self.status is not EntryStatus.PUBLISHED:
            return False  # a reserved name signed by the creator is held by the check, even if unchanged
        self.status, self.checks = EntryStatus.CHECKING, self.checks + 1
        return True

    @property
    def public(self) -> bool:
        return self.status is EntryStatus.PUBLISHED and self.video is not None and self.cover is not None

    def ready(self, cover: MediaRef, video: MediaRef, duration_ms: int) -> None:
        self.cover, self.video, self.duration_ms = cover, video, duration_ms

    def sign_as_admin(self, creator: Creator) -> None:
        """The admin changes the name or country: no check, and a reserved name becomes official."""
        if self.status is EntryStatus.CHECKING:
            raise InvalidValueError("The entry is being checked. Edit it in a minute.")
        self.creator = creator.as_official()

    def publish(self, at: datetime, reviewed_by: str = "", *, by_admin: bool = False) -> None:
        """Published by the check (never with a reserved name the admin has not signed) or by the admin."""
        if self.video is None or self.cover is None:
            raise InvalidValueError("an entry needs its video and cover before it is published")
        if by_admin:
            self.creator = self.creator.as_official()
        elif self.creator.held:
            raise InvalidValueError("a reserved name is published only by the admin")
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

    def published(
        self, *, style: str | None = None, featured: bool = False, country: str | None = None
    ) -> list[GalleryEntry]:
        """Public entries, newest first: all, the featured ones, one style or one creator country."""
        shown = [
            e
            for e in self.entries.values()
            if e.public and (style is None or e.style == style) and (country is None or e.creator.country == country)
        ]
        if featured:
            shown = [e for e in shown if e.featured]
        return sorted(shown, key=lambda e: e.published_at or e.submitted_at, reverse=True)

    def countries(self) -> dict[str, int]:
        """The creator countries of public entries, with how many entries each, most first."""
        counts: dict[str, int] = {}
        for e in self.entries.values():
            if e.public and e.creator.country:
                counts[e.creator.country] = counts.get(e.creator.country, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
