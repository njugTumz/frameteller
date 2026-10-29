"""Composition root: the only place that builds adapters and wires them into use cases."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from frameteller.application import jobs as job_kinds
from frameteller.application.budget import LimitBudgetGuard
from frameteller.application.events import JobUpdated
from frameteller.application.limits import ProjectAllowance, VisitorAllowance
from frameteller.application.ports import (
    Clock,
    CompositorPort,
    DirectorPort,
    IdGenerator,
    ImageGenerationPort,
    Job,
    MediaStoragePort,
    ProjectRepository,
    ReviewerPort,
    RubricLibrary,
    SegmentationPort,
    ShareIndex,
    SpeechToTextPort,
    SpendLedger,
    VideoRendererPort,
    VisitorQuota,
)
from frameteller.application.use_cases import (
    AcceptReview,
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
    MergeCharacters,
    MovePanelObject,
    OpenShare,
    PreSegmentPanel,
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
    SupervisePanel,
    TranscribeInstruction,
)
from frameteller.infrastructure.azure import (
    AzureBlobMediaStorage,
    BlobProjectRepository,
    BlobShareIndex,
    BlobSpendLedger,
    BlobVisitorQuota,
    blob_service,
)
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.imaging.compositor import PillowCompositor
from frameteller.infrastructure.imaging.ffmpeg_animatic import FfmpegVideoRenderer
from frameteller.infrastructure.imaging.share_preview import PillowSharePreview
from frameteller.infrastructure.imaging.storyboard_pdf import PillowStoryboardSheet
from frameteller.infrastructure.jobs import Handler, InProcessJobQueue, JobStatus
from frameteller.infrastructure.local import (
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
    sessions: ActiveSessions = field(default_factory=ActiveSessions)
    readiness: dict[str, ReadinessCheck] = field(default_factory=dict)
    glimmer_lease: GlimmerLease | None = None  # set by the warm-up script (POST /internal/glimmer/lease)


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
) -> Container:
    """Wire use cases to the given ports. Tests pass fakes; build_container() passes the real adapters."""
    ids = ids or RandomIds()
    compositor = compositor or PillowCompositor()  # local work, no network: tests use it too
    renderer = renderer or FfmpegVideoRenderer()
    hub = EventHub()
    clock = clock or SystemClock()
    limits = settings.demo_limits
    allowance = ProjectAllowance(repo, limits)
    budget = LimitBudgetGuard(
        ledger,
        clock,
        per_project_usd=settings.budget_per_project_usd,
        per_day_usd=settings.budget_per_day_usd,
    )

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

    handlers: dict[str, Handler] = {}
    queue = InProcessJobQueue(handlers, on_status=on_status)

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
    export_animatic = ExportAnimatic(repo, storage, renderer, hub)
    handlers[job_kinds.EXPORT_ANIMATIC] = handler(
        lambda p: export_animatic.execute(p["project_id"], subtitles=bool(p["subtitles"]), job_key=p["job_key"])
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

    correct_transcript = CorrectTranscript(repo, director, ids, request_cast, hub)
    open_share = OpenShare(repo, shares)
    return Container(
        settings=settings,
        storage=storage,
        jobs=queue,
        hub=hub,
        create_project=CreateProject(repo, ids, VisitorAllowance(quota, clock, limits) if quota else None),
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
        share_project=ShareProject(repo, shares, ids),
        revoke_share=RevokeShare(repo, shares),
        open_share=open_share,
        share_preview=SharePreview(open_share, storage, PillowSharePreview()),
        reorder_shots=ReorderShots(repo),
        voice_session=RunVoiceSession(
            speech,
            DirectTurn(repo, director, ids, max_shots=limits.shots_per_project),
            correct_transcript,
            request_cast,
            hub,
            ids,
            repo,
            storage,
            limits,
        ),
        correct_transcript=correct_transcript,
        transcribe_instruction=TranscribeInstruction(repo, speech),
        delete_narration=DeleteNarration(repo, storage),
        studio_status=GetStudioStatus(
            ledger, clock, per_day_usd=settings.budget_per_day_usd, paused=settings.demo_paused, limits=limits
        ),
        apply_fix=ApplySuggestedFix(repo, queue, request_cast),
        accept_review=AcceptReview(repo),
        continuity_checks=SetContinuityChecks(repo),
        readiness=readiness or {},
        glimmer_lease=glimmer_lease,
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
    quick = RetryPolicy(1, settings.glimmer_timeout_s)
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
    else:
        root = settings.local_storage_dir
        local_media = LocalFileMediaStorage(root)
        storage = local_media
        repo, ledger, check = JsonFileProjectRepository(root), FileSpendLedger(root), local_media.check_writable
        shares = FileShareIndex(root)
        quota = FileVisitorQuota(root)
    caller = ModelCaller(ledger, Breakers(settings.breaker_failures, settings.breaker_cooldown_s))
    client = meta_client(settings)
    lease = glimmer_lease(settings, storage)
    return wire(
        settings,
        repo=repo,
        storage=storage,
        director=MetaSparkDirectorAdapter(client, caller, settings),
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
    )
