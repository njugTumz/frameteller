"""The gallery document round-trips, including the creator's signature, and reads entries saved before it."""

from frameteller.domain import Creator, Gallery
from frameteller.infrastructure.local.gallery import gallery_from_dict, gallery_to_dict
from tests.domain.test_gallery import entry


def test_the_creator_and_its_checks_survive_a_round_trip() -> None:
    e = entry()
    e.creator, e.checks = Creator("Ama", "KE"), 2
    e.heart("b1")
    back = gallery_from_dict(gallery_to_dict(Gallery({e.id: e})))
    got = back.entries[e.id]
    assert (got.creator, got.checks, got.hearts, got.status) == (Creator("Ama", "KE"), 2, {"b1"}, e.status)


def test_entries_from_before_names_are_anonymous() -> None:
    doc = gallery_to_dict(Gallery({"g1": entry()}))
    for e in doc["entries"]:
        del e["creator"], e["checks"]
    got = gallery_from_dict(doc).entries["g1"]
    assert got.creator.anonymous
    assert got.checks == 0
