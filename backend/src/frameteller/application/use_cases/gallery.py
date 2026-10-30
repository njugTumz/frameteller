"""The public gallery (ADR 0017): submit with consent, moderate automatically, publish or hold for the admin.

A submission renders the gallery's own copy of the animatic (burned-in captions, the audio the creator chose)
and a cover, so later edits to the project never change what the gallery shows. The moderation review runs
the `gallery` rubric through the continuity supervisor's reviewer (Spark, or Glimmer screening when warm): a
clean, confident pass publishes the entry; anything else waits for the admin. A creator name with contact
details waits for the admin without a review. Renaming a published entry runs the review again (no new render).
Withdrawing deletes the entry and its media.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from frameteller.application import costs
from frameteller.application.errors import (
    ApplicationError,
    GalleryEntryNotFoundError,
    GallerySubmissionError,
)
from frameteller.application.jobs import gallery_job
from frameteller.application.limits import EXPORTS, ProjectAllowance
from frameteller.application.ports import (
    BudgetGuard,
    Clock,
    GalleryRepository,
    IdGenerator,
    JobQueuePort,
    MediaStoragePort,
    ProjectRepository,
    ReviewerPort,
    ReviewRequest,
    RubricLibrary,
    SharePreviewPort,
)
from frameteller.application.rubrics import RubricError, RubricSet
from frameteller.application.use_cases.export_animatic import AnimaticOptions, ExportAnimatic
from frameteller.application.use_cases.share import ShareProject
from frameteller.domain import (
    Animatic,
    Creator,
    Decision,
    DomainError,
    EntryStatus,
    Gallery,
    GalleryAudio,
    GalleryEntry,
    MediaRef,
    PanelStatus,
    Project,
)

log = logging.getLogger("frameteller.gallery")

RUBRIC = "gallery"
MIN_CONFIDENCE = 0.7  # below this a pass still waits for the admin
REVIEW_PANELS = 6
MAX_STORY_CHARS = 6000
COULD_NOT_CHECK = "The automatic check couldn't run, so a person will look at it."
NOT_SURE = "The automatic check wasn't sure, so a person will look at it."

AdminAction = Literal["publish", "hide", "feature", "unfeature"]


def _media(entry: GalleryEntry) -> list[MediaRef]:
    base = f"gallery/{entry.id}"
    refs = [MediaRef(f"{base}/animatic.mp4"), MediaRef(f"{base}/animatic.srt"), MediaRef(f"{base}/cover.webp")]
    return refs + [r for r in (entry.cover, entry.video) if r is not None and r not in refs]


async def _discard(storage: MediaStoragePort, entry: GalleryEntry) -> None:
    for ref in _media(entry):
        try:
            await storage.delete(ref)
        except Exception:
            log.warning("could not delete gallery media", extra={"key": ref.key}, exc_info=True)


def story_text(project: Project, creator: Creator | None = None) -> str:
    """What the moderation review reads: the creator's display name, the title, the cast and the story as told."""
    cast = "; ".join(f"{c.name}: {c.canonical_description}" for c in project.bible.characters.values())
    told = " ".join(t.text for t in project.turns)
    signed = creator.name if creator and creator.name else "none"
    text = f"Creator's display name, shown as the author: {signed}\nTitle: {project.title or 'Untitled'}\n"
    return f"{text}Characters: {cast or 'none'}\nStory: {told}"[:MAX_STORY_CHARS]


class SubmitToGallery:
    def __init__(
        self,
        repo: ProjectRepository,
        gallery: GalleryRepository,
        share: ShareProject,
        jobs: JobQueuePort,
        storage: MediaStoragePort,
        clock: Clock,
        ids: IdGenerator,
        *,
        voice_available: bool,
        allowance: ProjectAllowance | None = None,
    ) -> None:
        self._repo, self._gallery, self._share, self._jobs = repo, gallery, share, jobs
        self._storage, self._clock, self._ids = storage, clock, ids
        self._voice, self._allowance = voice_available, allowance

    async def execute(
        self, project_id: str, *, consent: bool, audio: GalleryAudio, creator: Creator | None = None
    ) -> GalleryEntry:
        if not consent:
            raise GallerySubmissionError("Tick the box to agree before you submit.")
        project = await self._repo.get(project_id)
        try:
            Animatic.from_project(project)
        except DomainError:
            raise GallerySubmissionError("Draw every shot before you submit to the gallery.") from None
        if audio == "mine" and not project.narrations:
            raise GallerySubmissionError("Your recording wasn't kept. Choose the Ava voice or no audio.")
        if audio == "voice" and not self._voice:
            raise GallerySubmissionError("The Ava voice isn't available right now. Choose your voice or no audio.")
        if self._allowance:
            self._allowance.check(project, EXPORTS)
        token = await self._share.execute(project_id, public=project.share_public)
        entry = GalleryEntry(
            self._ids.new_id(),
            project_id,
            token,
            project.title.strip() or "Untitled story",
            project.style.value,
            max(1, len({t.episode for t in project.turns})),
            len(project.shots),
            audio,
            self._clock.now(),
            creator=creator or Creator(),
        )
        previous = await self._gallery.update(lambda g: g.submit(entry))
        if previous is not None:
            await _discard(self._storage, previous)
        if await self._jobs.enqueue(gallery_job(project_id, entry.id)) and self._allowance:
            await self._allowance.spend(project_id, EXPORTS)
        return entry


@dataclass(frozen=True, slots=True)
class Moderation:
    publish: bool
    note: str
    model: str


class ProcessGallerySubmission:
    """Background job: render the gallery copy, run the moderation review, then publish or hold."""

    def __init__(
        self,
        repo: ProjectRepository,
        gallery: GalleryRepository,
        storage: MediaStoragePort,
        export: ExportAnimatic,
        preview: SharePreviewPort,
        reviewer: ReviewerPort,
        rubrics: RubricLibrary,
        budget: BudgetGuard,
        share: ShareProject,
        clock: Clock,
    ) -> None:
        self._repo, self._gallery, self._storage, self._export = repo, gallery, storage, export
        self._preview, self._reviewer, self._rubrics, self._budget = preview, reviewer, rubrics, budget
        self._share, self._clock = share, clock

    async def execute(self, project_id: str, entry_id: str) -> EntryStatus | None:
        entry = (await self._gallery.get()).find(entry_id)
        if entry is None or entry.status is not EntryStatus.CHECKING:
            return None  # withdrawn, or already done
        project = await self._repo.get(project_id)
        base = f"gallery/{entry_id}"
        rendered = entry.video is not None and entry.cover is not None  # a new name to check: no new render
        if not rendered:
            try:
                options = AnimaticOptions(subtitles=True, audio=entry.audio)
                export = await self._export.render(project, options, f"{base}/animatic")
                cover = await self._storage.put(f"{base}/cover.webp", await self._first_panel(project), "image/webp")
            except (ApplicationError, DomainError) as e:
                message = e.user_message if isinstance(e, ApplicationError) else str(e)
                await self._gallery.update(lambda g: _apply(g, entry_id, lambda en: en.fail(message)))
                return EntryStatus.FAILED
        verdict = await self._moderate(project, base, entry.creator)
        now = self._clock.now()

        def decide(en: GalleryEntry) -> None:
            if not rendered:
                en.ready(cover, export.video, export.duration_ms)
            if verdict.publish:
                en.publish(now, verdict.model)
            else:
                en.hold(verdict.note, verdict.model)

        status = await self._gallery.update(lambda g: _apply(g, entry_id, decide))
        if status is None:  # withdrawn while it rendered
            await _discard(self._storage, entry)
            return None
        if status is EntryStatus.PUBLISHED:
            await self._share.execute(project_id, public=True)  # gallery entries are indexable
        return status

    async def _first_panel(self, project: Project) -> bytes:
        panel = project.panels[project.shots[0].id]
        assert panel.shown_image is not None  # rendered: Animatic.from_project checked every panel
        return await self._storage.get(panel.shown_image)

    async def _moderate(self, project: Project, base: str, creator: Creator) -> Moderation:
        contact = creator.contact_details()
        if contact:  # a person decides; no review is needed to know that
            return Moderation(False, f"GAL-08: {contact}", "")
        sheet_ref = MediaRef(f"{base}/review.png")
        try:
            rubric = RubricSet((self._rubrics.get(RUBRIC),))
            panels = []
            for shot in project.shots[:REVIEW_PANELS]:
                panel = project.panels.get(shot.id)
                if panel is not None and panel.status is PanelStatus.READY and panel.shown_image is not None:
                    panels.append(await self._storage.get(panel.shown_image))
            sheet = await self._preview.contact_sheet(project.title, panels)
            await self._storage.put(sheet_ref.key, sheet, "image/png")
            await self._budget.charge(project.id, costs.REVIEW, "gallery moderation")
            request = ReviewRequest((sheet_ref,), rubric, project.style, subject=story_text(project, creator))
            verdict = await self._reviewer.review(request)
        except (ApplicationError, RubricError):
            log.warning("gallery moderation could not run", extra={"project_id": project.id}, exc_info=True)
            return Moderation(False, COULD_NOT_CHECK, "")
        finally:
            await self._storage.delete(sheet_ref)
        serious = [i for i in verdict.issues if i.serious]
        if verdict.decision is Decision.PASS and not serious and verdict.confidence >= MIN_CONFIDENCE:
            return Moderation(True, "", verdict.model)
        note = "; ".join(f"{i.rule_id}: {i.description}" for i in serious) or NOT_SURE
        return Moderation(False, note, verdict.model)


def _apply(gallery: Gallery, entry_id: str, change: Callable[[GalleryEntry], None]) -> EntryStatus | None:
    entry = gallery.find(entry_id)
    if entry is None:
        return None
    change(entry)
    return entry.status


class GalleryEntryOfProject:
    def __init__(self, gallery: GalleryRepository) -> None:
        self._gallery = gallery

    async def execute(self, project_id: str) -> GalleryEntry:
        entry = (await self._gallery.get()).of_project(project_id)
        if entry is None:
            raise GalleryEntryNotFoundError(project_id)
        return entry


class WithdrawFromGallery:
    """The creator takes their storyboard out of the gallery: the entry and its media are deleted."""

    def __init__(self, gallery: GalleryRepository, storage: MediaStoragePort) -> None:
        self._gallery, self._storage = gallery, storage

    async def execute(self, project_id: str) -> None:
        def take(g: Gallery) -> GalleryEntry | None:
            entry = g.of_project(project_id)
            return g.remove(entry.id) if entry is not None else None

        removed = await self._gallery.update(take)
        if removed is None:
            raise GalleryEntryNotFoundError(project_id)
        await _discard(self._storage, removed)


class SignGalleryEntry:
    """The creator adds, changes or removes the name and country on their entry. A new name is checked again."""

    def __init__(self, gallery: GalleryRepository, jobs: JobQueuePort) -> None:
        self._gallery, self._jobs = gallery, jobs

    async def execute(self, project_id: str, creator: Creator) -> GalleryEntry:
        def sign(g: Gallery) -> tuple[GalleryEntry, bool]:
            entry = g.of_project(project_id)
            if entry is None:
                raise GalleryEntryNotFoundError(project_id)
            return entry, entry.sign(creator)

        entry, check = await self._gallery.update(sign)
        if check:
            await self._jobs.enqueue(gallery_job(project_id, entry.id, entry.checks))
        return entry


class BrowseGallery:
    """What visitors see: published entries, featured or newest, optionally one style or one creator country."""

    def __init__(self, gallery: GalleryRepository) -> None:
        self._gallery = gallery

    async def execute(
        self, *, featured: bool = False, style: str | None = None, country: str | None = None
    ) -> list[GalleryEntry]:
        return (await self._gallery.get()).published(style=style, featured=featured, country=country)

    async def countries(self) -> dict[str, int]:
        """Creator countries across the whole gallery, for the counter and the filter."""
        return (await self._gallery.get()).countries()

    async def creator_of(self, project_id: str) -> Creator | None:
        """How a project's public entry is signed, for its share page; None when it isn't in the gallery."""
        entry = (await self._gallery.get()).of_project(project_id)
        return entry.creator if entry is not None and entry.public else None

    async def entry(self, entry_id: str) -> GalleryEntry:
        entry = (await self._gallery.get()).find(entry_id)
        if entry is None or not entry.public:
            raise GalleryEntryNotFoundError(entry_id)
        return entry


class HeartGalleryEntry:
    def __init__(self, gallery: GalleryRepository) -> None:
        self._gallery = gallery

    async def execute(self, entry_id: str, visitor: str) -> int:
        """The entry's hearts after this visitor's one heart."""

        def heart(g: Gallery) -> int:
            entry = g.find(entry_id)
            if entry is None or not entry.public:
                raise GalleryEntryNotFoundError(entry_id)
            entry.heart(visitor)
            return len(entry.hearts)

        return await self._gallery.update(heart)


class ReportGalleryEntry:
    def __init__(self, gallery: GalleryRepository, clock: Clock) -> None:
        self._gallery, self._clock = gallery, clock

    async def execute(self, entry_id: str, visitor: str, reason: str) -> None:
        now = self._clock.now()

        def report(g: Gallery) -> bool:
            entry = g.find(entry_id)
            if entry is None or not entry.public:
                raise GalleryEntryNotFoundError(entry_id)
            return entry.report(visitor, reason, now)

        if await self._gallery.update(report):
            log.warning("gallery entry hidden by reports", extra={"entry_id": entry_id})


class ModerateGallery:
    """The admin's decisions: every entry, publish, hide, feature, remove."""

    def __init__(self, gallery: GalleryRepository, storage: MediaStoragePort, share: ShareProject, clock: Clock):
        self._gallery, self._storage, self._share, self._clock = gallery, storage, share, clock

    async def entries(self) -> list[GalleryEntry]:
        entries = (await self._gallery.get()).entries.values()
        return sorted(entries, key=lambda e: e.submitted_at, reverse=True)

    async def act(self, entry_id: str, action: AdminAction) -> GalleryEntry:
        now = self._clock.now()

        def apply(g: Gallery) -> GalleryEntry:
            entry = g.find(entry_id)
            if entry is None:
                raise GalleryEntryNotFoundError(entry_id)
            if action == "publish":
                entry.publish(now)
            elif action == "hide":
                entry.hide("Hidden by the admin.")
            else:
                entry.feature(action == "feature")
            return entry

        entry = await self._gallery.update(apply)
        if action == "publish":
            await self._share.execute(entry.project_id, public=True)
        return entry

    async def remove(self, entry_id: str) -> None:
        removed = await self._gallery.update(lambda g: g.remove(entry_id))
        if removed is None:
            raise GalleryEntryNotFoundError(entry_id)
        await _discard(self._storage, removed)
