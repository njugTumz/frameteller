"""Gallery use cases: consent, the moderation paths, withdraw, hearts, reports and the admin's actions."""

import pytest

from frameteller.application.errors import GalleryEntryNotFoundError, GallerySubmissionError, ModelUnavailableError
from frameteller.application.jobs import GALLERY_SUBMISSION
from frameteller.application.use_cases import ExportAnimatic, GeneratePanel, ShareProject
from frameteller.application.use_cases.gallery import (
    COULD_NOT_CHECK,
    BrowseGallery,
    HeartGalleryEntry,
    ModerateGallery,
    ProcessGallerySubmission,
    ReportGalleryEntry,
    SubmitToGallery,
    WithdrawFromGallery,
)
from frameteller.domain import Decision, EntryStatus, GalleryAudio, Issue, MediaRef, Narration, Severity
from tests.application.conftest import World
from tests.fakes import (
    FakeReviewer,
    FakeSharePreview,
    FakeSpeechSynthesis,
    FakeVideoRenderer,
    FixedClock,
    InMemoryGalleryRepository,
    InMemoryRubricLibrary,
    InMemoryShareIndex,
    RecordingPublisher,
    SequentialIds,
    verdict,
)


class Gallery:
    """The use cases around one World, with a scripted reviewer."""

    def __init__(self, w: World, *verdicts: object, voice: bool = True) -> None:
        self.w, self.repo, self.clock = w, InMemoryGalleryRepository(), FixedClock()
        self.shares, self.renderer = InMemoryShareIndex(), FakeVideoRenderer()
        self.reviewer = FakeReviewer(*verdicts)  # type: ignore[arg-type]
        self.synthesis = FakeSpeechSynthesis(w.storage)
        self.share = ShareProject(w.repo, self.shares, SequentialIds("tok"))
        export = ExportAnimatic(
            w.repo, w.storage, self.renderer, RecordingPublisher(), None, w.budget, self.synthesis if voice else None
        )
        self.submit = SubmitToGallery(
            w.repo, self.repo, self.share, w.jobs, w.storage, self.clock, SequentialIds("g"), voice_available=voice
        )
        self.process = ProcessGallerySubmission(
            w.repo, self.repo, w.storage, export, FakeSharePreview(), self.reviewer, InMemoryRubricLibrary(),
            w.budget, self.share, self.clock,
        )  # fmt: skip

    async def submitted(self, audio: GalleryAudio = "none") -> EntryStatus | None:
        for shot_id in ("s1", "s2", "s3"):
            await GeneratePanel(self.w.repo, self.w.images, self.w.budget, self.w.jobs).execute("p1", shot_id, 1)
        entry = await self.submit.execute("p1", consent=True, audio=audio)
        assert self.w.jobs.jobs[-1].kind == GALLERY_SUBMISSION
        return await self.process.execute("p1", entry.id)

    async def entry(self):  # type: ignore[no-untyped-def]
        return (await self.repo.get()).of_project("p1")


async def test_without_consent_nothing_is_submitted(world: World) -> None:
    g = Gallery(world)
    with pytest.raises(GallerySubmissionError, match="Tick the box"):
        await g.submit.execute("p1", consent=False, audio="none")
    assert await g.entry() is None


async def test_every_shot_must_be_drawn_and_my_voice_must_have_been_kept(world: World) -> None:
    g = Gallery(world)
    with pytest.raises(GallerySubmissionError, match="Draw every shot"):
        await g.submit.execute("p1", consent=True, audio="none")
    for shot_id in ("s1", "s2", "s3"):
        await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", shot_id, 1)
    with pytest.raises(GallerySubmissionError, match="recording wasn't kept"):
        await g.submit.execute("p1", consent=True, audio="mine")
    with pytest.raises(GallerySubmissionError, match="Brandon voice isn't available"):
        await Gallery(world, voice=False).submit.execute("p1", consent=True, audio="voice")


async def test_a_clean_review_publishes_with_captions_burned_in_and_makes_the_share_page_indexable(
    world: World,
) -> None:
    g = Gallery(world)  # the fake reviewer passes with confidence 0.9
    assert await g.submitted() is EntryStatus.PUBLISHED
    e = await g.entry()
    assert e is not None
    assert e.public
    assert e.reviewed_by == "fake-reviewer"
    assert e.video == MediaRef(f"gallery/{e.id}/animatic.mp4")
    assert world.storage.files[f"gallery/{e.id}/cover.webp"][0] == world.storage.files[e.cover.key][0]  # type: ignore[union-attr]
    _, _, recordings, captions = g.renderer.rendered[0]
    assert recordings == {}  # "none": silent
    assert captions is not None
    assert captions.burn
    assert world.project().share_public
    assert world.project().animatic is None  # the gallery's copy is not the project's animatic
    assert f"gallery/{e.id}/review.png" not in world.storage.files  # the moderation sheet is not kept
    assert ("p1", 0.006, "gallery moderation") in world.budget.charges
    rubric = g.reviewer.requests[0].rubric.rubrics[0]
    assert rubric.id == "gallery"
    assert "Title: The Lantern Cat" in g.reviewer.requests[0].subject


async def test_a_doubtful_review_waits_for_the_admin(world: World) -> None:
    issue = Issue("GAL-02", Severity.BLOCKER, "The cat looks like a famous cartoon cat.")
    g = Gallery(world, verdict(Decision.ASK, issue, confidence=0.8))
    assert await g.submitted() is EntryStatus.PENDING
    e = await g.entry()
    assert e is not None
    assert e.note == "GAL-02: The cat looks like a famous cartoon cat."
    assert e.video is not None  # rendered, so the admin can watch it
    assert not world.project().share_public


async def test_an_unsure_pass_and_a_failed_check_both_wait(world: World) -> None:
    g = Gallery(world, verdict(confidence=0.5))
    assert await g.submitted() is EntryStatus.PENDING
    g = Gallery(world, ModelUnavailableError("muse-spark-1.3"))
    assert await g.submitted() is EntryStatus.PENDING
    e = await g.entry()
    assert e is not None
    assert e.note == COULD_NOT_CHECK


async def test_the_brandon_voice_reads_each_shot_instead_of_mine(world: World) -> None:
    p = world.project()
    p.keep_narration(Narration("t1", MediaRef("projects/p1/narration/t1.wav"), 4000))
    await world.repo.save(p)
    g = Gallery(world)
    assert await g.submitted("voice") is EntryStatus.PUBLISHED
    assert [call[1] for call in g.synthesis.calls] == ["en-US-BrandonMultilingualNeural"] * 3
    animatic, _, recordings, _ = g.renderer.rendered[0]
    assert all(len(c.audio) == 1 and c.audio[0].end_ms <= c.duration_ms for c in animatic.clips)
    assert recordings  # the voice clips were mixed in, then deleted
    assert not any(k.startswith("gallery/") and k.endswith(".wav") for k in world.storage.files)


async def test_withdraw_deletes_the_entry_and_its_media(world: World) -> None:
    g = Gallery(world)
    await g.submitted()
    e = await g.entry()
    assert e is not None
    await WithdrawFromGallery(g.repo, world.storage).execute("p1")
    assert await g.entry() is None
    assert not any(k.startswith(f"gallery/{e.id}/") for k in world.storage.files)
    with pytest.raises(GalleryEntryNotFoundError):
        await WithdrawFromGallery(g.repo, world.storage).execute("p1")


async def test_a_withdrawal_while_checking_is_never_published(world: World) -> None:
    g = Gallery(world)
    for shot_id in ("s1", "s2", "s3"):
        await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", shot_id, 1)
    e = await g.submit.execute("p1", consent=True, audio="none")
    await WithdrawFromGallery(g.repo, world.storage).execute("p1")
    assert await g.process.execute("p1", e.id) is None
    assert not g.renderer.rendered


async def test_hearts_reports_and_the_admin(world: World) -> None:
    g = Gallery(world)
    await g.submitted()
    e = await g.entry()
    assert e is not None
    heart = HeartGalleryEntry(g.repo)
    assert await heart.execute(e.id, "b1") == 1
    assert await heart.execute(e.id, "b1") == 1
    report = ReportGalleryEntry(g.repo, g.clock)
    for visitor in ("v1", "v2", "v3"):
        await report.execute(e.id, visitor, "not original")
    browse = BrowseGallery(g.repo)
    assert await browse.execute() == []  # hidden by reports
    with pytest.raises(GalleryEntryNotFoundError):
        await heart.execute(e.id, "b2")

    admin = ModerateGallery(g.repo, world.storage, g.share, g.clock)
    assert [x.status for x in await admin.entries()] == [EntryStatus.HIDDEN]
    await admin.act(e.id, "publish")
    await admin.act(e.id, "feature")
    assert [x.id for x in await browse.execute(featured=True)] == [e.id]
    await admin.act(e.id, "hide")
    assert await browse.execute() == []
    await admin.remove(e.id)
    assert await admin.entries() == []
    assert not any(k.startswith(f"gallery/{e.id}/") for k in world.storage.files)
