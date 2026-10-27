"""Value objects for media that lives outside the domain (Blob Storage keys)."""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.domain.errors import InvalidValueError


@dataclass(frozen=True, slots=True)
class MediaRef:
    """Opaque reference to a stored file. Never a signed URL (CLAUDE.md section 5)."""

    key: str

    def __post_init__(self) -> None:
        if not self.key or "://" in self.key:
            raise InvalidValueError(f"media key must be a storage key, not {self.key!r}")
