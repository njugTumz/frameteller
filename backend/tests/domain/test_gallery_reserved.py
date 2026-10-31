"""Reserved display names (ADR 0017): matched without case, spaces or punctuation; official only from the admin."""

from datetime import UTC, datetime

import pytest

from frameteller.domain import RESERVED_NAMES, Creator, EntryStatus, GalleryEntry, InvalidValueError, MediaRef

NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "name",
    [
        *RESERVED_NAMES,
        "frameteller TEAM",
        "Frame-Teller",
        "FRAMETELLER.OFFICIAL",
        "M.E.T.A.",
        "muse!",
        "Cerebral   Valley",
        "cerebral-valley",
        "\uff2d\uff45\uff54\uff41",  # full-width letters: "Meta" after NFKC
    ],
)
def test_reserved_names_ignore_case_spaces_and_punctuation(name: str) -> None:
    creator = Creator.of(name, None)
    assert creator.reserved
    assert creator.held  # signed by a creator: never official
    assert not creator.official


@pytest.mark.parametrize("name", ["", "Metal", "Musee", "Frameteller fan", "Team Frame", "Valley", "Ama"])
def test_other_names_are_not_reserved(name: str) -> None:
    assert not Creator.of(name, None).reserved


def published(creator: Creator) -> GalleryEntry:
    entry = GalleryEntry("e1", "p1", "tok", "Story", "pencil", 1, 3, "none", NOW, creator=creator)
    entry.ready(MediaRef("c.webp"), MediaRef("v.mp4"), 1000)
    return entry


def test_only_the_admin_publishes_a_reserved_name_and_that_makes_it_official() -> None:
    entry = published(Creator("Frameteller team"))
    with pytest.raises(InvalidValueError, match="only by the admin"):
        entry.publish(NOW)
    entry.publish(NOW, by_admin=True)
    assert entry.creator == Creator("Frameteller team", "", official=True)


def test_the_admin_publishing_any_other_name_adds_no_badge() -> None:
    entry = published(Creator("Ama", "KE"))
    entry.publish(NOW, by_admin=True)
    assert not entry.creator.official


def test_the_admin_signs_a_reserved_name_without_a_check_and_the_status_stays() -> None:
    entry = published(Creator("Ama"))
    entry.publish(NOW)
    entry.sign_as_admin(Creator.of("Frameteller team", None))
    assert entry.status is EntryStatus.PUBLISHED
    assert entry.creator.official


def test_a_creator_signing_a_reserved_name_is_always_checked_even_unchanged() -> None:
    entry = published(Creator("Frameteller team"))
    entry.publish(NOW, by_admin=True)
    assert entry.sign(Creator.of("Frameteller team", "US")) is True  # the creator's own edit: not official any more
    assert entry.status is EntryStatus.CHECKING
    assert not entry.creator.official
