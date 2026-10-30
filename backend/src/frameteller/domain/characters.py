"""Characters, the character bible and cast approval (ADR 0004). A character can change clothes during the story:
each outfit is a look with its own reference sheet (ADR 0018)."""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field, replace
from enum import StrEnum

from frameteller.domain.errors import InvalidValueError, MissingReferenceError, UnknownCharacterError
from frameteller.domain.media import MediaRef


class CastStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


EVERYDAY = "everyday"  # the look of the canonical description and its sheet
LOOK_ID = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


@dataclass(frozen=True, slots=True)
class Look:
    """Another outfit of the same character ("Farmer costume"): same face, hair and build, different clothes."""

    id: str
    label: str
    clothes: str  # what they wear in this look, and nothing else
    reference: MediaRef | None = None

    def __post_init__(self) -> None:
        if not LOOK_ID.match(self.id) or self.id == EVERYDAY:
            raise InvalidValueError(f"look {self.id!r}: needs a short lowercase id other than {EVERYDAY!r}")
        if not self.label.strip() or not self.clothes.strip():
            raise InvalidValueError(f"look {self.id!r}: needs a label and the clothes")


@dataclass(frozen=True, slots=True)
class Character:
    id: str
    name: str
    canonical_description: str
    reference: MediaRef | None = None
    looks: tuple[Look, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.name.strip() or not self.canonical_description.strip():
            raise InvalidValueError("a character needs an id, a name and a canonical description")

    def look(self, look_id: str) -> Look:
        for look in self.looks:
            if look.id == look_id:
                return look
        raise UnknownCharacterError(f"{self.id} has no look {look_id!r}")

    def has_look(self, look_id: str) -> bool:
        return any(look.id == look_id for look in self.looks)

    def dressed(self, look: Look | None) -> Character:
        """The character as a shot shows them: in `look`, with its sheet. None: the everyday look."""
        if look is None:
            return self
        clothes = look.clothes.strip().rstrip(".")
        return replace(
            self,
            canonical_description=f"{self.canonical_description.strip().rstrip('.')}. In this shot {self.name} "
            f"wears the {look.label.strip().lower()}: {clothes}, instead of any clothes described before",
            reference=look.reference or self.reference,
        )


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
        """Add a character or change its description. A changed description drops the old reference, and the
        sheets of its looks, which were drawn from it."""
        existing = self.characters.get(character.id)
        if existing is not None and existing.canonical_description == character.canonical_description:
            character = replace(character, reference=character.reference or existing.reference)
        elif existing is not None:
            looks = character.looks or existing.looks
            character = replace(character, looks=tuple(replace(lk, reference=None) for lk in looks))
        if existing != character:
            self.characters[character.id] = character
            self.status = CastStatus.DRAFT

    def rename(self, character_id: str, name: str) -> Character:
        """A new name only: the sheet still shows the same character, so approval stands."""
        renamed = replace(self.get(character_id), name=name.strip())
        if not renamed.name:
            raise InvalidValueError("a character needs a name")
        self.characters[character_id] = renamed
        return renamed

    def remove(self, character_id: str) -> Character:
        """Drop a character. The rest of the cast keeps its sheets and its approval."""
        removed = self.get(character_id)
        del self.characters[character_id]
        if not self.characters:
            self.status = CastStatus.DRAFT
        return removed

    def set_reference(self, character_id: str, reference: MediaRef) -> None:
        self.characters[character_id] = replace(self.get(character_id), reference=reference)
        self.status = CastStatus.DRAFT

    def set_look(self, character_id: str, look: Look) -> bool:
        """Add a look, or change its clothes or label. Changed clothes drop its sheet. True if anything changed."""
        character = self.get(character_id)
        existing = next((lk for lk in character.looks if lk.id == look.id), None)
        if existing is not None:
            look = replace(look, reference=existing.reference if existing.clothes == look.clothes else None)
            if look == existing:
                return False
            looks = tuple(look if lk.id == look.id else lk for lk in character.looks)
        else:
            looks = (*character.looks, look)
        self.characters[character_id] = replace(character, looks=looks)
        if look.reference is None:
            self.status = CastStatus.DRAFT
        return True

    def set_look_reference(self, character_id: str, look_id: str, reference: MediaRef) -> None:
        character = self.get(character_id)
        character.look(look_id)
        looks = tuple(replace(lk, reference=reference) if lk.id == look_id else lk for lk in character.looks)
        self.characters[character_id] = replace(character, looks=looks)
        self.status = CastStatus.DRAFT

    def approve(self, unworn: Collection[str] = ()) -> None:
        """`unworn`: looks no shot shows ("wren/farmer_costume"), which need no sheet yet."""
        missing = sorted(
            [c.id for c in self.characters.values() if c.reference is None]
            + [
                target
                for c in self.characters.values()
                for lk in c.looks
                if lk.reference is None and (target := f"{c.id}/{lk.id}") not in unworn
            ]
        )
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


def sheet_target(character_id: str, look_id: str | None = None) -> str:
    """How jobs and failures name one sheet: "wren", or "wren/farmer_costume" for a look."""
    return f"{character_id}/{look_id}" if look_id and look_id != EVERYDAY else character_id


def split_target(target: str) -> tuple[str, str | None]:
    character_id, _, look_id = target.partition("/")
    return character_id, (look_id or None)


@dataclass(frozen=True, slots=True)
class SheetRefusal:
    """Muse Image refused a sheet twice (ADR 0019). `text` is the description (or an outfit's clothes) it refused;
    `suggestion` is a plainer one to offer. Trying the same text again is pointless until it changes."""

    text: str
    suggestion: str
