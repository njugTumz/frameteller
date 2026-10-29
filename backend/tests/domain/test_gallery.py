"""Gallery entries: one heart per browser, reports hide, only published entries are shown or featured."""

from datetime import UTC, datetime, timedelta

import pytest

from frameteller.domain import REPORTS_TO_HIDE, EntryStatus, Gallery, GalleryEntry, InvalidValueError, MediaRef

T0 = datetime(2026, 11, 2, 17, 0, tzinfo=UTC)


def entry(n: int = 1, *, project: str = "p1", style: str = "pencil", published: bool = True) -> GalleryEntry:
    e = GalleryEntry(f"g{n}", project, f"tok{n}", f"Story {n}", style, 1, 3, "mine", T0 + timedelta(minutes=n))
    e.ready(MediaRef(f"gallery/g{n}/cover.webp"), MediaRef(f"gallery/g{n}/animatic.mp4"), 9000)
    if published:
        e.publish(T0 + timedelta(minutes=n), "fake-reviewer")
    return e


def test_a_heart_counts_once_per_browser() -> None:
    e = entry()
    assert e.heart("b1")
    assert not e.heart("b1")
    assert e.heart("b2")
    assert len(e.hearts) == 2


def test_enough_reports_from_different_visitors_hide_a_published_entry() -> None:
    e = entry()
    for n in range(REPORTS_TO_HIDE - 1):
        assert not e.report(f"v{n}", "looks like a film character", T0)
    assert not e.report("v0", "again", T0)  # one report per visitor
    assert e.status is EntryStatus.PUBLISHED
    assert e.report("v-last", "x" * 500, T0)
    assert e.status is EntryStatus.HIDDEN
    assert len(e.reports[-1].reason) == 300
    assert not e.public


def test_only_a_published_entry_can_be_featured_and_hiding_unfeatures() -> None:
    pending = entry(published=False)
    pending.hold("not sure")
    with pytest.raises(InvalidValueError):
        pending.feature(True)
    e = entry()
    e.feature(True)
    e.hide("by the admin")
    assert not e.featured


def test_publishing_needs_the_video_and_cover() -> None:
    e = GalleryEntry("g1", "p1", "tok", "t", "pencil", 1, 1, "none", T0)
    with pytest.raises(InvalidValueError):
        e.publish(T0)


def test_the_listing_shows_public_entries_newest_first_by_style_or_featured() -> None:
    g = Gallery()
    for e in (entry(1), entry(2, project="p2", style="paper_cutout"), entry(3, project="p3", published=False)):
        g.submit(e)
    g.entries["g1"].feature(True)
    assert [e.id for e in g.published()] == ["g2", "g1"]
    assert [e.id for e in g.published(style="pencil")] == ["g1"]
    assert [e.id for e in g.published(featured=True)] == ["g1"]


def test_a_project_has_one_entry_and_resubmitting_replaces_it() -> None:
    g = Gallery()
    g.submit(entry(1))
    previous = g.submit(entry(2))  # same project
    assert previous is not None
    assert previous.id == "g1"
    assert list(g.entries) == ["g2"]
