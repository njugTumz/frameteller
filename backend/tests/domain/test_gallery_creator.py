"""The creator's optional signature on a gallery entry: validation, contact details, edits, countries."""

import pytest

from frameteller.domain import Creator, EntryStatus, Gallery, InvalidValueError
from frameteller.domain.countries import COUNTRIES
from tests.domain.test_gallery import entry


def test_a_name_is_one_trimmed_line_of_at_most_40_characters_and_both_fields_are_optional() -> None:
    assert Creator.of("  Ama   the\tstoryteller ", "ke") == Creator("Ama the storyteller", "KE")
    assert Creator.of(None, None) == Creator()
    assert Creator.of("", "").anonymous
    assert Creator.of("x" * 40, None).name == "x" * 40
    with pytest.raises(InvalidValueError, match="at most 40"):
        Creator.of("x" * 41, None)
    with pytest.raises(InvalidValueError, match="control characters"):
        Creator.of("Ama​B", None)


def test_only_a_country_from_the_list() -> None:
    assert len(COUNTRIES) == 249
    assert Creator.of(None, "ae").country == "AE"
    for bad in ("XX", "UK", "KEN", "1"):
        with pytest.raises(InvalidValueError, match="from the list"):
            Creator.of(None, bad)


@pytest.mark.parametrize("name", ["Ama", "Captain Biscuit", "Zoë & Kofi", "Studio 42", "Mr. Fox", "J.R. Doodles"])
def test_ordinary_names_and_nicknames_are_clean(name: str) -> None:
    assert Creator(name).contact_details() is None


@pytest.mark.parametrize(
    ("name", "why"),
    [
        ("ama@example.com", "email"),
        ("see https://example.com", "link"),
        ("www.amadraws", "link"),
        ("amadraws.com", "link"),
        ("follow @amadraws", "social handle"),
        ("@amadraws", "social handle"),
        ("Ama +971 50 123 4567", "phone number"),
        ("call 0501234567", "phone number"),
    ],
)
def test_contact_details_in_a_name_are_found(name: str, why: str) -> None:
    found = Creator(name).contact_details()
    assert found is not None
    assert why in found


def test_a_new_name_on_a_published_entry_is_checked_again_but_removing_or_a_country_is_not() -> None:
    e = entry()
    assert not e.sign(Creator("", "KE"))  # a country, from the list: shown at once
    assert e.status is EntryStatus.PUBLISHED
    assert e.sign(Creator("Ama", "KE"))  # a new name: out of the gallery until checked
    assert (e.status, e.checks) == (EntryStatus.CHECKING, 1)
    with pytest.raises(InvalidValueError, match="being checked"):
        e.sign(Creator())
    e.publish(e.submitted_at)
    assert not e.sign(Creator("Ama", "AE"))  # the same name
    assert not e.sign(Creator())  # removed: an anonymous storyteller again
    assert e.creator.anonymous
    assert e.status is EntryStatus.PUBLISHED


def test_a_pending_entry_keeps_waiting_for_a_person_when_renamed() -> None:
    e = entry()
    e.hold("A person will look.")
    assert not e.sign(Creator("Ama"))
    assert e.status is EntryStatus.PENDING
    assert e.creator.name == "Ama"


def test_the_gallery_filters_and_counts_creator_countries_of_public_entries_only() -> None:
    g = Gallery()
    for n, country in enumerate(["KE", "KE", "AE", "", "JP"], start=1):
        e = entry(n, project=f"p{n}", published=n != 5)
        e.creator = Creator(f"Maker {n}", country)
        g.submit(e)
    assert g.countries() == {"KE": 2, "AE": 1}  # JP's entry is not published
    assert [e.id for e in g.published(country="KE")] == ["g2", "g1"]
    assert g.published(country="JP") == []
    assert len(g.published()) == 4
