import pytest

from frameteller.domain import (
    CastStatus,
    Character,
    CharacterBible,
    InvalidValueError,
    MediaRef,
    MissingReferenceError,
    UnknownCharacterError,
)
from tests.builders import CAT, MIRA


def approved_bible() -> CharacterBible:
    bible = CharacterBible()
    for c in (MIRA, CAT):
        bible.upsert(c)
        bible.set_reference(c.id, MediaRef(f"refs/{c.id}.webp"))
    bible.approve()
    return bible


def test_new_bible_is_draft() -> None:
    assert CharacterBible().status is CastStatus.DRAFT


def test_cast_approves_when_every_character_has_a_reference() -> None:
    assert approved_bible().is_approved


def test_cast_cannot_be_approved_with_a_missing_reference() -> None:
    bible = CharacterBible()
    bible.upsert(MIRA)
    bible.upsert(CAT)
    bible.set_reference("mira", MediaRef("refs/mira.webp"))
    with pytest.raises(MissingReferenceError, match="cat"):
        bible.approve()


def test_empty_cast_cannot_be_approved() -> None:
    with pytest.raises(MissingReferenceError):
        CharacterBible().approve()


def test_new_character_returns_cast_to_draft() -> None:
    bible = approved_bible()
    bible.upsert(Character("owl", "Owl", "a small brown owl"))
    assert bible.status is CastStatus.DRAFT


def test_changed_description_returns_cast_to_draft_and_drops_reference() -> None:
    bible = approved_bible()
    bible.upsert(Character("mira", "Mira", "8-year-old girl in a red raincoat"))
    assert bible.status is CastStatus.DRAFT
    assert bible.get("mira").reference is None


def test_same_character_again_keeps_approval_and_reference() -> None:
    bible = approved_bible()
    bible.upsert(MIRA)
    assert bible.is_approved
    assert bible.get("mira").reference == MediaRef("refs/mira.webp")


def test_new_reference_returns_cast_to_draft() -> None:
    bible = approved_bible()
    bible.set_reference("cat", MediaRef("refs/cat-v2.webp"))
    assert bible.status is CastStatus.DRAFT


def test_unknown_character_is_rejected() -> None:
    with pytest.raises(UnknownCharacterError):
        approved_bible().get("dragon")
    with pytest.raises(UnknownCharacterError, match="dragon"):
        approved_bible().require(("mira", "dragon"))


def test_character_needs_name_and_description() -> None:
    with pytest.raises(InvalidValueError):
        Character("x", " ", "something")
    with pytest.raises(InvalidValueError):
        Character("x", "X", "")


def test_media_ref_rejects_urls() -> None:
    with pytest.raises(InvalidValueError):
        MediaRef("https://example.blob.core.windows.net/x.webp?sig=abc")
    with pytest.raises(InvalidValueError):
        MediaRef("")
