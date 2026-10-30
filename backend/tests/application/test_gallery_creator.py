"""The creator's name and country on a gallery entry: moderation of the name, edits, and the recheck."""

import pytest

from frameteller.application.jobs import GALLERY_SUBMISSION
from frameteller.application.use_cases import GeneratePanel
from frameteller.application.use_cases.gallery import BrowseGallery, SignGalleryEntry
from frameteller.domain import Creator, Decision, EntryStatus, InvalidValueError, Issue, Severity
from tests.application.conftest import World
from tests.application.test_gallery import Gallery
from tests.fakes import verdict


async def signed(g: Gallery, creator: Creator) -> EntryStatus | None:
    for shot_id in ("s1", "s2", "s3"):
        await GeneratePanel(g.w.repo, g.w.images, g.w.budget, g.w.jobs).execute("p1", shot_id, 1)
    entry = await g.submit.execute("p1", consent=True, audio="none", creator=creator)
    return await g.process.execute("p1", entry.id)


async def test_a_clean_name_is_reviewed_with_the_story_and_published(world: World) -> None:
    g = Gallery(world)
    assert await signed(g, Creator("Captain Biscuit", "KE")) is EntryStatus.PUBLISHED
    assert "Creator's display name, shown as the author: Captain Biscuit" in g.reviewer.requests[0].subject
    e = await g.entry()
    assert e is not None
    assert e.creator == Creator("Captain Biscuit", "KE")
    assert await BrowseGallery(g.repo).creator_of("p1") == Creator("Captain Biscuit", "KE")


async def test_an_unsigned_entry_tells_the_review_there_is_no_name(world: World) -> None:
    g = Gallery(world)
    assert await signed(g, Creator()) is EntryStatus.PUBLISHED
    assert "shown as the author: none" in g.reviewer.requests[0].subject


async def test_a_name_with_contact_details_waits_for_a_person_without_a_review(world: World) -> None:
    g = Gallery(world)
    assert await signed(g, Creator("ama@example.com")) is EntryStatus.PENDING
    e = await g.entry()
    assert e is not None
    assert e.note == "GAL-08: The name has an email address."
    assert e.video is not None  # rendered, so the admin can watch it
    assert g.reviewer.requests == []  # a person decides: no credits spent on a review
    assert await BrowseGallery(g.repo).creator_of("p1") is None  # not public, so no share page byline


async def test_a_slur_or_a_public_figure_flagged_by_the_review_waits_for_a_person(world: World) -> None:
    issue = Issue("GAL-08", Severity.BLOCKER, "The name is a famous singer's.")
    g = Gallery(world, verdict(Decision.ASK, issue, confidence=0.9))
    assert await signed(g, Creator("A Famous Singer")) is EntryStatus.PENDING
    e = await g.entry()
    assert e is not None
    assert e.note == "GAL-08: The name is a famous singer's."


async def test_a_new_name_is_checked_again_without_a_new_render_and_removing_is_immediate(world: World) -> None:
    g = Gallery(world)
    await signed(g, Creator())
    sign = SignGalleryEntry(g.repo, world.jobs)

    e = await sign.execute("p1", Creator("", "AE"))  # only a country: shown at once, no check
    assert e.status is EntryStatus.PUBLISHED
    assert len(g.reviewer.requests) == 1

    e = await sign.execute("p1", Creator("Ama", "AE"))
    assert e.status is EntryStatus.CHECKING
    job = world.jobs.jobs[-1]
    assert (job.kind, job.idempotency_key) == (GALLERY_SUBMISSION, f"{GALLERY_SUBMISSION}:p1:{e.id}:1")
    assert await g.process.execute("p1", e.id) is EntryStatus.PUBLISHED
    assert len(g.renderer.rendered) == 1  # the gallery copy is kept
    assert "shown as the author: Ama" in g.reviewer.requests[-1].subject
    assert await BrowseGallery(g.repo).creator_of("p1") == Creator("Ama", "AE")

    e = await sign.execute("p1", Creator())
    assert e.status is EntryStatus.PUBLISHED
    assert e.creator.anonymous
    assert len(g.reviewer.requests) == 2


async def test_a_new_name_that_fails_its_check_takes_the_entry_out_until_a_person_looks(world: World) -> None:
    g = Gallery(world)
    await signed(g, Creator("Ama"))
    e = await SignGalleryEntry(g.repo, world.jobs).execute("p1", Creator("call 0501234567"))
    assert await g.process.execute("p1", e.id) is EntryStatus.PENDING
    assert await BrowseGallery(g.repo).execute() == []


async def test_no_edit_while_the_first_check_runs_and_none_without_an_entry(world: World) -> None:
    g = Gallery(world)
    for shot_id in ("s1", "s2", "s3"):
        await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", shot_id, 1)
    await g.submit.execute("p1", consent=True, audio="none")
    with pytest.raises(InvalidValueError, match="being checked"):
        await SignGalleryEntry(g.repo, world.jobs).execute("p1", Creator("Ama"))
