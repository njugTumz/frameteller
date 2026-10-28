"""Composition root: the only place that builds adapters and wires them into use cases."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from frameteller.application import jobs as job_kinds
from frameteller.application.budget import LimitBudgetGuard
from frameteller.application.events import JobUpdated
from frameteller.application.ports import (
    Clock,
    CompositorPort,
    DirectorPort,
    IdGenerator,
    ImageGenerationPort,
    Job,
    MediaStoragePort,
    ProjectRepository,
    SegmentationPort,
    ShareIndex,
    SpeechToTextPort,
    SpendLedger,
    VideoRendererPort,
)
from frameteller.application.use_cases import (
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
    RevokeShare,
    RunVoiceSession,
    SegmentObjectAtPoint,
    SharePreview,
    ShareProject,
    TranscribeInstruction,
)
from frameteller.infrastructure.azure import (
    AzureBlobMediaStorage,
    BlobProjectRepository,
    BlobShareIndex,
    BlobSpendLedger,
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
    JsonFileProjectRepository,
    LocalFileMediaStorage,
)
from frameteller.infrastructure.meta import meta_client
from frameteller.infrastructure.meta.director import MetaSparkDirectorAdapter
from frameteller.infrastructure.meta.image import MetaImageAdapter
from frameteller.infrastructure.meta.sam import MetaSamAdapter
from frameteller.infrastructure.meta.voice import MetaVoiceTranscribeAdapter
from frameteller.infrastructure.observability import log_context
from frameteller.infrastructure.resilience import Breakers, ModelCaller
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
    sessions: ActiveSessions = field(default_factory=ActiveSessions)
    readiness: dict[str, ReadinessCheck] = field(default_factory=dict)


def wire(
    settings: Settings,
    *,
    repo: ProjectRepository,
    storage: MediaStoragePort,
    director: DirectorPort,
    images: ImageGenerationPort,
    segmentation: SegmentationPort,
    speech: SpeechToTextPort,
    ledger: SpendLedger,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    readiness: dict[str, ReadinessCheck] | None = None,
    compositor: CompositorPort | None = None,
    renderer: VideoRendererPort | None = None,
    shares: ShareIndex,
) -> Container:
    """Wire use cases to the given ports. Tests pass fakes; build_container() passes the real adapters."""
    ids = ids or RandomIds()
    compositor = compositor or PillowCompositor()  # local work, no network: tests use it too
    renderer = renderer or FfmpegVideoRenderer()
    hub = EventHub()
    budget = LimitBudgetGuard(
        ledger,
        clock or SystemClock(),
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
    edit_by_command = EditPanelByCommand(repo, director, EditPanelAppearance(repo, images, budget, queue))
    cast_references = GenerateCastReferences(GenerateCharacterReference(repo, images, budget), hub)
    request_cast = RequestCastReferences(repo, queue, ids)

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
        lambda p: cast_references.execute(p["project_id"], p["character_ids"].split(","))
    )

    correct_transcript = CorrectTranscript(repo, director, ids, request_cast, hub)
    open_share = OpenShare(repo, shares)
    return Container(
        settings=settings,
        storage=storage,
        jobs=queue,
        hub=hub,
        create_project=CreateProject(repo, ids),
        get_project=GetProject(repo),
        find_shot=FindShot(repo),
        approve_cast=ApproveCast(repo, queue, ids),
        request_cast=request_cast,
        rename_character=RenameCharacter(repo),
        remove_character=RemoveCharacter(repo),
        merge_characters=MergeCharacters(repo, queue),
        request_render=RequestPanelRender(repo, queue),
        request_edit=RequestPanelEdit(repo, queue),
        select_object=SegmentObjectAtPoint(repo, segmentation, budget, ids),
        move_object=MovePanelObject(repo, queue),
        request_animatic=RequestAnimaticExport(repo, queue),
        storyboard_pdf=ExportStoryboardPdf(repo, storage, PillowStoryboardSheet()),
        share_project=ShareProject(repo, shares, ids),
        revoke_share=RevokeShare(repo, shares),
        open_share=open_share,
        share_preview=SharePreview(open_share, storage, PillowSharePreview()),
        reorder_shots=ReorderShots(repo),
        voice_session=RunVoiceSession(
            speech, DirectTurn(repo, director, ids), correct_transcript, request_cast, hub, ids, repo, storage
        ),
        correct_transcript=correct_transcript,
        transcribe_instruction=TranscribeInstruction(repo, speech),
        delete_narration=DeleteNarration(repo, storage),
        readiness=readiness or {},
    )


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
    else:
        root = settings.local_storage_dir
        local_media = LocalFileMediaStorage(root)
        storage = local_media
        repo, ledger, check = JsonFileProjectRepository(root), FileSpendLedger(root), local_media.check_writable
        shares = FileShareIndex(root)
    caller = ModelCaller(ledger, Breakers(settings.breaker_failures, settings.breaker_cooldown_s))
    client = meta_client(settings)
    return wire(
        settings,
        repo=repo,
        storage=storage,
        director=MetaSparkDirectorAdapter(client, caller, settings),
        images=MetaImageAdapter(client, caller, storage, settings),
        segmentation=MetaSamAdapter(client, caller, storage, settings),
        speech=MetaVoiceTranscribeAdapter(caller, settings),
        ledger=ledger,
        readiness={"storage": check},
        shares=shares,
    )
