"""Characters, the character bible and cast approval (ADR 0004)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from frameteller.domain.errors import InvalidValueError, MissingReferenceError, UnknownCharacterError
from frameteller.domain.media import MediaRef


class CastStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


@dataclass(frozen=True, slots=True)
class Character:
    id: str
    name: str
    canonical_description: str
    reference: MediaRef | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.name.strip() or not self.canonical_description.strip():
            raise InvalidValueError("a character needs an id, a name and a canonical description")


@dataclass(slots=True)
class CharacterBible:
    """One canonical description per character. Any change returns the cast to draft."""

    characters: dict[str, Character] = field(default_factory=dict)
    status: CastStatus = CastStatus.DRAFT

    def __contains__(self, character_id: object) -> bool:
        return character_id in self.characters

    def get(self, character_id: str) -> Character:
        try:
            return self.characters[character_id]
        except KeyError:
            raise UnknownCharacterError(f"character {character_id!r} is not in the bible") from None

    def upsert(self, character: Character) -> None:
        """Add a character or change its description. A changed description drops the old reference."""
        existing = self.characters.get(character.id)
        if existing is not None and existing.canonical_description == character.canonical_description:
            character = replace(character, reference=character.reference or existing.reference)
        if existing != character:
            self.characters[character.id] = character
            self.status = CastStatus.DRAFT

    def set_reference(self, character_id: str, reference: MediaRef) -> None:
        self.characters[character_id] = replace(self.get(character_id), reference=reference)
        self.status = CastStatus.DRAFT

    def approve(self) -> None:
        missing = sorted(c.id for c in self.characters.values() if c.reference is None)
        if not self.characters or missing:
            raise MissingReferenceError(f"cannot approve the cast; missing reference sheets: {missing or 'all'}")
        self.status = CastStatus.APPROVED

    @property
    def is_approved(self) -> bool:
        return self.status is CastStatus.APPROVED

    def require(self, character_ids: tuple[str, ...]) -> None:
        unknown = sorted(set(character_ids) - self.characters.keys())
        if unknown:
            raise UnknownCharacterError(f"characters not in the bible: {unknown}")
