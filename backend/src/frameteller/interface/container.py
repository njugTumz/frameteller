"""Composition root: the only place that builds adapters and wires them into use cases."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx2
from openai import AsyncOpenAI

from frameteller.application import jobs as job_kinds
from frameteller.application.budget import LimitBudgetGuard
from frameteller.application.capacity import Capacity, GatedImages, GatedSegmentation
from frameteller.application.events import JobUpdated
from frameteller.application.incidents import IncidentDesk, RecordingEvents, ReportProblem, RetryFailedJob
from frameteller.application.judge import JudgeDesk, JudgePassesToday
from frameteller.application.lanes import Lane
from frameteller.application.limits import ProjectAllowance, SpeechAllowance, VisitorAllowance
from frameteller.application.ports import (
    Clock,
    CompositorPort,
    DirectorPort,
    GalleryRepository,
    IdGenerator,
    ImageGenerationPort,
    Job,
    MediaStoragePort,
    ProjectRepository,
    ReviewerPort,
    RubricLibrary,
    SegmentationPort,
    ShareIndex,
    SpeechSynthesisPort,
    SpeechToTextPort,
    SpendLedger,
    TranslatorPort,
    VideoRendererPort,
    VisitorQuota,
)
from frameteller.application.use_cases import (
    AcceptReview,
    AnimaticOptions,
    ApplySuggestedFix,
    ApproveCast,
    ComposePanel,
    CorrectTranscript,
    CreateProject,
    DeleteNarration,
    DirectTurn,
    EditPanelAppearance,
    EditPanelByCommand,
    ExportAnimatic,
    ExportStoryboardPdf,
    FindShot,
    GenerateCastReferences,
    GenerateCharacterReference,
    GeneratePanel,
    GetProject,
    GetStudioStatus,
    ListVoices,
    MergeCharacters,
    MovePanelObject,
    OpenShare,
    PreSegmentPanel,
    PreviewVoice,
    ReadScript,
    RemoveCharacter,
    RenameCharacter,
    ReorderShots,
    RequestAnimaticExport,
    RequestCastReferences,
    RequestPanelEdit,
    RequestPanelRender,
    ReviewSheet,
    RevokeShare,
    RunVoiceSession,
    SegmentObjectAtPoint,
    SetContinuityChecks,
    SharePreview,
    ShareProject,
    StoryDirector,
    SupervisePanel,
    TranscribeInstruction,
)
from frameteller.application.use_cases.gallery import (
    BrowseGallery,
    GalleryEntryOfProject,
    HeartGalleryEntry,
    ModerateGallery,
    ProcessGallerySubmission,
    ReportGalleryEntry,
    SignGalleryEntry,
    SubmitToGallery,
    WithdrawFromGallery,
)
from frameteller.infrastructure.azure import (
    AzureBlobMediaStorage,
    BlobGalleryRepository,
    BlobProjectRepository,
    BlobShareIndex,
    BlobSpendLedger,
    BlobVisitorQuota,
    blob_service,
)
from frameteller.infrastructure.azure.speech import AzureSpeechSynthesizer
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.imaging.compositor import PillowCompositor
from frameteller.infrastructure.imaging.ffmpeg_animatic import FfmpegVideoRenderer
from frameteller.infrastructure.imaging.share_preview import PillowSharePreview
from frameteller.infrastructure.imaging.storyboard_pdf import PillowStoryboardSheet
from frameteller.infrastructure.jobs import Handler, InProcessJobQueue, JobStatus
from frameteller.infrastructure.local import (
    FileGalleryRepository,
    FileShareIndex,
    FileSpendLedger,
    FileVisitorQuota,
    JsonFileProjectRepository,
    LocalFileMediaStorage,
)
from frameteller.infrastructure.meta import meta_client
from frameteller.infrastructure.meta.director import MetaSparkDirectorAdapter
from frameteller.infrastructure.meta.image import MetaImageAdapter
from frameteller.infrastructure.meta.sam import MetaSamAdapter
from frameteller.infrastructure.meta.voice import MetaVoiceTranscribeAdapter
from frameteller.infrastructure.observability import log_context
from frameteller.infrastructure.resilience import Breakers, ModelCaller, RetryPolicy
from frameteller.infrastructure.review import (
    FallbackReviewer,
    FileRubricLibrary,
    GlimmerLease,
    GlimmerReviewerAdapter,
    SparkReviewerAdapter,
    WarmGatedReviewer,
)
from frameteller.infrastructure.system import RandomIds, SystemClock
from frameteller.interface.hub import ActiveSessions, EventHub

ReadinessCheck = Callable[[], Awaitable[None]]


@dataclass
class Container:
    settings: Settings
    storage: MediaStoragePort
    jobs: InProcessJobQueue
    hub: EventHub
    create_project: CreateProject
    get_project: GetProject
    find_shot: FindShot
    approve_cast: ApproveCast
    request_cast: RequestCastReferences
    rename_character: RenameCharacter
    remove_character: RemoveCharacter
    merge_characters: MergeCharacters
    request_render: RequestPanelRender
    request_edit: RequestPanelEdit
    select_object: SegmentObjectAtPoint
    request_animatic: RequestAnimaticExport
    storyboard_pdf: ExportStoryboardPdf
    share_project: ShareProject
    revoke_share: RevokeShare
    open_share: OpenShare
    share_preview: SharePreview
    move_object: MovePanelObject
    reorder_shots: ReorderShots
    voice_session: RunVoiceSession
    correct_transcript: CorrectTranscript
    transcribe_instruction: TranscribeInstruction
    delete_narration: DeleteNarration
    studio_status: GetStudioStatus
    apply_fix: ApplySuggestedFix
    accept_review: AcceptReview
    continuity_checks: SetContinuityChecks
    capacity: Capacity = field(default_factory=Capacity)
    sessions: ActiveSessions = field(default_factory=ActiveSessions)
    readiness: dict[str, ReadinessCheck] = field(default_factory=dict)
    glimmer_lease: GlimmerLease | None = None  # set by the warm-up script (POST /internal/glimmer/lease)
    # "Read it to me" (ADR 0015): None when Text-to-Speech is not configured.
    read_script: ReadScript | None = None
    list_voices: ListVoices | None = None
    preview_voice: PreviewVoice | None = None
    # The gallery (ADR 0017).
    submit_to_gallery: SubmitToGallery | None = None
    gallery_entry: GalleryEntryOfProject | None = None
    withdraw_from_gallery: WithdrawFromGallery | None = None
    sign_gallery: SignGalleryEntry | None = None
    browse_gallery: BrowseGallery | None = None
    heart_gallery: HeartGalleryEntry | None = None
    report_gallery: ReportGalleryEntry | None = None
    moderate_gallery: ModerateGallery | None = None
    # The judge pass (ADR 0016): passes seen, the admin's reserve override, and today's activity per pass.
    judge_desk: JudgeDesk | None = None
    incidents: IncidentDesk | None = None
    report_problem: ReportProblem | None = None
    retry_job: RetryFailedJob | None = None
    judge_passes: JudgePassesToday | None = None


def wire(
    settings: Settings,
    *,
    repo: ProjectRepository,
    storage: MediaStoragePort,
    director: DirectorPort,
    images: ImageGenerationPort,
    segmentation: SegmentationPort,
    speech: SpeechToTextPort,
    reviewer: ReviewerPort,
    rubrics: RubricLibrary,
    ledger: SpendLedger,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    readiness: dict[str, ReadinessCheck] | None = None,
    compositor: CompositorPort | None = None,
    renderer: VideoRendererPort | None = None,
    shares: ShareIndex,
    quota: VisitorQuota | None = None,
    glimmer_lease: GlimmerLease | None = None,
    synthesizer: SpeechSynthesisPort | None = None,
    translator: TranslatorPort | None = None,
    gallery: GalleryRepository | None = None,
    incidents: IncidentDesk | None = None,
) -> Container:
    """Wire use cases to the given ports. Tests pass fakes; build_container() passes the real adapters."""
    ids = ids or RandomIds()
    compositor = compositor or PillowCompositor()  # local work, no network: tests use it too
    renderer = renderer or FfmpegVideoRenderer()
    hub = EventHub()
    clock = clock or SystemClock()
    incidents = incidents or IncidentDesk(storage, clock, settings.budget_calendar.day)
    events = RecordingEvents(hub, incidents)  # session failures also go to the admin's Errors tab
    limits = settings.demo_limits
    allowance = ProjectAllowance(repo, limits)
    calendar = settings.budget_calendar
    desk = JudgeDesk(storage)
    budget = LimitBudgetGuard(
        ledger, clock, per_project_usd=settings.budget_per_project_usd, calendar=calendar, desk=desk
    )
    # ADR 0016: model calls in flight are limited globally; past a limit, work waits in line.
    capacity = Capacity(settings.capacity_limits)
    images = GatedImages(images, capacity.images)
    segmentation = GatedSegmentation(segmentation, capacity.sam)

    async def on_status(job: Job, status: JobStatus, message: str | None) -> None:
        revision = job.payload.get("revision")
        event = JobUpdated(
            job.kind,
            job.idempotency_key,
            status.value,
            job.payload.get("shot_id"),
            int(revision) if revision else None,
            message,
        )
        await hub.publish(job.payload["project_id"], event)

    async def on_waiting(job: Job, place: int, estimate_s: float) -> None:
        revision = job.payload.get("revision")
        event = JobUpdated(
            job.kind,
            job.idempotency_key,
            "queued" if place else "running",
            job.payload.get("shot_id"),
            int(revision) if revision else None,
            position=place or None,
            estimate_s=estimate_s if place else None,
        )
        await hub.publish(job.payload["project_id"], event)

    handlers: dict[str, Handler] = {}
    queue = InProcessJobQueue(
        handlers,
        concurrency=settings.capacity_jobs,
        on_status=on_status,
        # Exports (and the gallery's copy) never hold up drawing.
        lanes={job_kinds.EXPORT_ANIMATIC: capacity.exports, job_kinds.GALLERY_SUBMISSION: capacity.exports},
        on_waiting=on_waiting,
        on_failure=incidents.job_failed,
    )

    generate_panel = GeneratePanel(repo, images, budget, queue)
    pre_segment = PreSegmentPanel(repo, segmentation, budget, queue)
    compose_panel = ComposePanel(repo, images, storage, compositor, budget)
    edit_appearance = EditPanelAppearance(repo, images, budget, queue)
    edit_by_command = EditPanelByCommand(repo, director, edit_appearance)
    cast_references = GenerateCastReferences(GenerateCharacterReference(repo, images, budget, queue), hub)
    request_cast = RequestCastReferences(repo, queue, ids)
    supervise_panel = SupervisePanel(repo, reviewer, rubrics, edit_appearance, budget, hub, clock)
    review_sheet = ReviewSheet(repo, reviewer, rubrics, budget, hub, clock)

    def handler(run: Callable[[dict[str, str]], Awaitable[object]]) -> Handler:
        async def handle(job: Job) -> None:
            with log_context(project_id=job.payload["project_id"]):
                await run(job.payload)

        return handle

    handlers[job_kinds.GENERATE_PANEL] = handler(
        lambda p: generate_panel.execute(
            p["project_id"], p["shot_id"], int(p["revision"]), "high" if p["quality"] == "high" else "low"
        )
    )
    handlers[job_kinds.PRE_SEGMENT_PANEL] = handler(
        lambda p: pre_segment.execute(p["project_id"], p["shot_id"], int(p["revision"]))
    )
    handlers[job_kinds.COMPOSE_PANEL] = handler(
        lambda p: compose_panel.execute(p["project_id"], p["shot_id"], int(p["revision"]))
    )
    export_animatic = ExportAnimatic(repo, storage, renderer, hub, translator, budget, synthesizer)
    handlers[job_kinds.EXPORT_ANIMATIC] = handler(
        lambda p: export_animatic.execute(p["project_id"], AnimaticOptions.of(p), job_key=p["job_key"])
    )
    handlers[job_kinds.EDIT_PANEL] = handler(
        lambda p: edit_by_command.execute(p["project_id"], p["shot_id"], p["instruction"])
    )
    handlers[job_kinds.GENERATE_CAST] = handler(
        lambda p: cast_references.execute(
            p["project_id"], p["character_ids"].split(","), correction=p.get("correction", "")
        )
    )
    handlers[job_kinds.SUPERVISE_PANEL] = handler(
        lambda p: supervise_panel.execute(
            p["project_id"], p["shot_id"], int(p["revision"]), "high" if p["quality"] == "high" else "low"
        )
    )
    handlers[job_kinds.REVIEW_SHEET] = handler(
        lambda p: review_sheet.execute(p["project_id"], p["character_id"], p["reference"])
    )

    share_project = ShareProject(repo, shares, ids)
    share_sheet = PillowSharePreview()
    submit = entry = withdraw = sign = browse = heart = report = moderate = None
    if gallery is not None:
        process = ProcessGallerySubmission(
            repo, gallery, storage, export_animatic, share_sheet, reviewer, rubrics, budget, share_project, clock
        )
        handlers[job_kinds.GALLERY_SUBMISSION] = handler(lambda p: process.execute(p["project_id"], p["entry_id"]))
        voice = synthesizer is not None
        submit = SubmitToGallery(
            repo, gallery, share_project, queue, storage, clock, ids, voice_available=voice, allowance=allowance
        )
        entry, withdraw = GalleryEntryOfProject(gallery), WithdrawFromGallery(gallery, storage)
        sign = SignGalleryEntry(gallery, queue)
        browse, heart, report = BrowseGallery(gallery), HeartGalleryEntry(gallery), ReportGalleryEntry(gallery, clock)
        moderate = ModerateGallery(gallery, storage, share_project, clock)

    correct_transcript = CorrectTranscript(repo, director, ids, request_cast, hub)
    open_share = OpenShare(repo, shares)
    direct_turn = DirectTurn(repo, director, ids, max_shots_per_episode=limits.shots_per_episode)
    read_script = list_voices = preview_voice = None
    if synthesizer is not None and translator is not None:
        speech_allowance = (
            SpeechAllowance(quota, clock, limits, settings.speech_characters_per_day) if quota is not None else None
        )
        story = StoryDirector(direct_turn, correct_transcript, request_cast, events, limits)
        read_script = ReadScript(synthesizer, translator, story, events, ids, repo, storage, budget, speech_allowance)
        list_voices = ListVoices(synthesizer)
        preview_voice = PreviewVoice(list_voices, synthesizer, storage, budget)
    studio_status = GetStudioStatus(
        ledger, clock, calendar=calendar, paused=settings.demo_paused, limits=limits, desk=desk
    )

    async def budget_open() -> bool:
        """A retry runs on the public budget: refused while the studio is paused or today's cap is spent."""
        status = await studio_status.execute(Lane.PUBLIC)
        return not status.paused and not status.full

    return Container(
        settings=settings,
        storage=storage,
        jobs=queue,
        hub=hub,
        create_project=CreateProject(
            repo, ids, VisitorAllowance(quota, clock, limits, day=calendar.day, desk=desk) if quota else None
        ),
        get_project=GetProject(repo),
        find_shot=FindShot(repo),
        approve_cast=ApproveCast(repo, queue, ids),
        request_cast=request_cast,
        rename_character=RenameCharacter(repo),
        remove_character=RemoveCharacter(repo),
        merge_characters=MergeCharacters(repo, queue),
        request_render=RequestPanelRender(repo, queue, allowance),
        request_edit=RequestPanelEdit(repo, queue, allowance),
        select_object=SegmentObjectAtPoint(repo, segmentation, budget, ids),
        move_object=MovePanelObject(repo, queue),
        request_animatic=RequestAnimaticExport(repo, queue, allowance),
        storyboard_pdf=ExportStoryboardPdf(repo, storage, PillowStoryboardSheet()),
        share_project=share_project,
        revoke_share=RevokeShare(repo, shares),
        open_share=open_share,
        share_preview=SharePreview(open_share, storage, share_sheet),
        reorder_shots=ReorderShots(repo),
        voice_session=RunVoiceSession(
            speech,
            direct_turn,
            correct_transcript,
            request_cast,
            events,
            ids,
            repo,
            storage,
            limits,
        ),
        correct_transcript=correct_transcript,
        transcribe_instruction=TranscribeInstruction(repo, speech),
        delete_narration=DeleteNarration(repo, storage),
        studio_status=studio_status,
        capacity=capacity,
        apply_fix=ApplySuggestedFix(repo, queue, request_cast),
        accept_review=AcceptReview(repo),
        continuity_checks=SetContinuityChecks(repo),
        readiness=readiness or {},
        glimmer_lease=glimmer_lease,
        read_script=read_script,
        list_voices=list_voices,
        preview_voice=preview_voice,
        submit_to_gallery=submit,
        gallery_entry=entry,
        withdraw_from_gallery=withdraw,
        sign_gallery=sign,
        browse_gallery=browse,
        heart_gallery=heart,
        report_gallery=report,
        moderate_gallery=moderate,
        judge_desk=desk,
        incidents=incidents,
        report_problem=ReportProblem(incidents, repo, quota, ids, clock, calendar.day),
        retry_job=RetryFailedJob(incidents, queue, budget_open),
        judge_passes=JudgePassesToday(desk, quota, ledger, clock, calendar.day),
    )


def build_reviewer(
    settings: Settings,
    client: AsyncOpenAI,
    caller: ModelCaller,
    storage: MediaStoragePort,
    lease: GlimmerLease | None = None,
) -> ReviewerPort:
    """REVIEWER: Muse Spark on Meta's API, Muse Glimmer on our Modal endpoint, or Glimmer with Spark behind it.

    With a lease, fallback and screen use Glimmer only while the lease says it is warm, and Spark otherwise."""
    spark = SparkReviewerAdapter(
        client,
        caller,
        storage,
        settings.director,
        RetryPolicy(settings.retry_attempts, settings.text_timeout_s),
        settings.reviewer_effort,
    )
    if settings.reviewer == "spark":
        return spark
    assert settings.glimmer_api_key is not None  # checked by the settings validator
    glimmer_client = AsyncOpenAI(
        base_url=settings.glimmer_base_url.strip(),
        api_key=settings.glimmer_api_key.get_secret_value(),
        max_retries=0,
    )
    if settings.reviewer == "glimmer":
        policy = RetryPolicy(settings.retry_attempts, settings.text_timeout_s)
        return GlimmerReviewerAdapter(glimmer_client, caller, storage, settings.glimmer_model, policy)
    # One short try: a cold or slow Glimmer hands the review to Spark at once instead of retrying.
    quick = RetryPolicy(1, settings.glimmer_timeout_s, rate_limited_attempts=1)
    glimmer = GlimmerReviewerAdapter(glimmer_client, caller, storage, settings.glimmer_model, quick)
    screen = settings.reviewer == "screen"
    if lease is None:
        return FallbackReviewer(glimmer, spark, confirm_flags=screen)
    warm = FallbackReviewer(glimmer, spark, confirm_flags=screen, on_primary_failed=lease.lost)
    return WarmGatedReviewer(warm, spark, lease)


def glimmer_lease(settings: Settings, storage: MediaStoragePort) -> GlimmerLease | None:
    if settings.reviewer in ("fallback", "screen") and settings.glimmer_only_when_warm:
        return GlimmerLease(storage, SystemClock())
    return None


def build_container(settings: Settings) -> Container:
    """Real adapters: Meta models, and local files or Azure Blob Storage (STORAGE_BACKEND) for persistence."""
    repo: ProjectRepository
    ledger: SpendLedger
    if settings.storage_backend == "blob":
        service = blob_service(settings)
        blob_media = AzureBlobMediaStorage(service.get_container_client(settings.azure_media_container))
        projects = service.get_container_client(settings.azure_projects_container)
        storage: MediaStoragePort = blob_media
        repo, ledger, check = BlobProjectRepository(projects), BlobSpendLedger(projects), blob_media.check_writable
        shares: ShareIndex = BlobShareIndex(projects)
        quota: VisitorQuota = BlobVisitorQuota(projects)
        gallery: GalleryRepository = BlobGalleryRepository(projects)
    else:
        root = settings.local_storage_dir
        local_media = LocalFileMediaStorage(root)
        storage = local_media
        repo, ledger, check = JsonFileProjectRepository(root), FileSpendLedger(root), local_media.check_writable
        shares = FileShareIndex(root)
        quota = FileVisitorQuota(root)
        gallery = FileGalleryRepository(root)
    incidents = IncidentDesk(storage, SystemClock(), settings.budget_calendar.day)
    caller = ModelCaller(ledger, Breakers(settings.breaker_failures, settings.breaker_cooldown_s), incidents=incidents)
    client = meta_client(settings)
    lease = glimmer_lease(settings, storage)
    director = MetaSparkDirectorAdapter(client, caller, settings)
    synthesizer = None
    if settings.azure_speech_key is not None:
        synthesizer = AzureSpeechSynthesizer(httpx2.AsyncClient(), caller, storage, settings)
    return wire(
        settings,
        repo=repo,
        storage=storage,
        director=director,
        synthesizer=synthesizer,
        translator=director,
        images=MetaImageAdapter(client, caller, storage, settings),
        segmentation=MetaSamAdapter(client, caller, storage, settings),
        speech=MetaVoiceTranscribeAdapter(caller, settings),
        reviewer=build_reviewer(settings, client, caller, storage, lease),
        glimmer_lease=lease,
        rubrics=FileRubricLibrary(settings.rubrics_path),
        ledger=ledger,
        readiness={"storage": check},
        shares=shares,
        quota=quota,
        gallery=gallery,
        incidents=incidents,
    )
