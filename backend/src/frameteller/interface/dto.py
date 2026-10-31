"""Request and response DTOs. Separate from domain entities: the API can change shape without touching rules."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from frameteller.application.events import (
    CastProposed,
    JobUpdated,
    NoSpeechHeard,
    ParagraphVoiced,
    ProjectEvent,
    ReadingPaused,
    ReadingResumed,
    ScriptAccepted,
    SessionEnded,
    SessionFailed,
    ShotCreated,
    ShotsReplaced,
    ShotUpdated,
    SupervisorFixed,
    SupervisorNeedsUser,
    SupervisorReviewed,
    TeleprompterAdvanced,
    TranscriptUpdated,
    TurnFinished,
)
from frameteller.application.ports import Quality, SpeechMode, SpeechOptions
from frameteller.application.use_cases import (
    AnimaticOptions,
    Beat,
    CastReview,
    JobTicket,
    OfferedVoice,
    Selection,
    StudioStatus,
    TranscriptCorrection,
)
from frameteller.application.use_cases.correct_transcript import MAX_TURN_CHARS
from frameteller.application.use_cases.voices import LANGUAGES
from frameteller.domain import (
    RESERVED_NOTE,
    AnimaticExport,
    Box,
    CanvasTransform,
    Character,
    Creator,
    EntryStatus,
    GalleryAudio,
    GalleryEntry,
    MediaRef,
    ObjectMask,
    Outcome,
    Panel,
    PanelStyle,
    Project,
    Script,
    SheetReview,
    Shot,
    SupervisorEntry,
    TranscriptTurn,
    Verdict,
    sheet_target,
)
from frameteller.domain.gallery import MAX_NAME_CHARS, MAX_REPORT_CHARS

Id = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


def media_url(ref: MediaRef | None) -> str | None:
    return f"/media/{ref.key}" if ref else None


# ---- requests ----


class ProjectCreate(BaseModel):
    title: str = Field(default="", max_length=120)
    style: Literal["pencil", "paper_cutout"] = Field(default="pencil", description="How every panel is drawn.")

    def as_style(self) -> PanelStyle:
        return PanelStyle(self.style)


class CastApproval(BaseModel):
    """Optional corrected descriptions by character id. A changed description redraws that sheet first."""

    descriptions: dict[str, str] = Field(default_factory=dict, max_length=50)


class CharacterRename(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class CharacterMerge(BaseModel):
    """Merge this character into `into`: every shot of it shows `into` instead."""

    into: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")


class RenderRequest(BaseModel):
    quality: Literal["draft", "final"] = "draft"

    def as_quality(self) -> Quality:
        return "high" if self.quality == "final" else "low"


class EditRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=500, examples=["her coat is red now"])


class SelectRequest(BaseModel):
    """A click on the panel as shown: (x, y) in a preview of preview_width x preview_height pixels."""

    x: int = Field(ge=0, le=20_000)
    y: int = Field(ge=0, le=20_000)
    preview_width: int = Field(ge=1, le=20_000)
    preview_height: int = Field(ge=1, le=20_000)


class LayerRequest(BaseModel):
    """Move, resize or delete a selected object: its cut-out's top-left moves by (dx, dy) panel pixels and it
    scales from that corner. dx = dy = 0 and scale = 1 moves it back home."""

    object_id: str = Field(min_length=1, max_length=200, examples=["character:mira"])
    dx: int = Field(default=0, ge=-20_000, le=20_000)
    dy: int = Field(default=0, ge=-20_000, le=20_000)
    scale: float = Field(default=1.0, ge=0.2, le=3.0)
    deleted: bool = False


class AnimaticRequest(BaseModel):
    subtitles: bool = Field(
        default=True,
        description="Burn the captions into the picture (English, French, Spanish, Portuguese). The MP4 always has "
        "them as a soft track, and an .srt is kept beside it.",
    )
    caption_language: str | None = Field(
        default=None,
        pattern=r"^[a-z]{2}(-[A-Z]{2})?$",
        description="Translate the captions (Muse Spark) into this locale, e.g. fr-FR. None: as spoken.",
    )

    def options(self) -> AnimaticOptions:
        return AnimaticOptions(self.subtitles, self.caption_language)


class ReorderRequest(BaseModel):
    shot_ids: list[str] = Field(min_length=1, max_length=500)


MAX_SCRIPT_BYTES = 16_000  # far above the script limit: accept_script gives the friendly message
# The languages a narrator can say they speak, by code: the same nine as "Read it to me" (any other: auto).
SPEAKING_LANGUAGES = {code: locale for code, (locale, _) in LANGUAGES.items()}


class SessionStart(BaseModel):
    """First WebSocket message. Mode and keywords are fixed for the session (CLAUDE.md section 5).

    "teleprompter" and "read" take a `script` (ADR 0015). "read" also takes a `voice` and `language` from GET
    /voices, and then receives no audio: the client sends pause, continue and end. In the other modes `language`
    is the language the narrator speaks (one of SPEAKING_LANGUAGES), passed to the transcriber as its language
    bias; without it the transcriber detects the language.
    """

    mode: Literal["narrate", "co_direct", "teleprompter", "read"] = "narrate"
    keywords: list[str] = Field(default_factory=list, max_length=50)
    keep_audio: bool = Field(default=False, description="The narrator agreed to keep the recording for the animatic.")
    script: str | None = Field(default=None, max_length=MAX_SCRIPT_BYTES, description="Pasted or uploaded text.")
    script_format: Literal["text", "markdown", "fountain"] = "text"
    voice: str | None = Field(default=None, pattern=r"^[A-Za-z]{2,3}-[A-Za-z]{2,4}-[A-Za-z]{3,40}$")
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")

    @property
    def scripted(self) -> bool:
        return self.mode in ("teleprompter", "read")

    def as_options(self) -> SpeechOptions:
        mode = SpeechMode.CO_DIRECTION if self.mode == "co_direct" else SpeechMode.NARRATION
        keywords = tuple(dict.fromkeys(k.strip()[:40] for k in self.keywords if k.strip()))
        bias = SPEAKING_LANGUAGES.get((self.language or "").split("-")[0]) if self.mode != "read" else None
        return SpeechOptions(mode=mode, keywords=keywords, language_bias=bias)


class ClientEnd(BaseModel):
    type: Literal["end"]


class ClientBeat(BaseModel):
    """ "A new shot starts now" (ADR 0008). Its time is where the audio received so far ends."""

    type: Literal["beat"]

    def at(self, received_ms: int) -> Beat:
        return Beat(received_ms)


class ClientCorrection(BaseModel):
    type: Literal["transcript.corrected"]
    turn_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=MAX_TURN_CHARS)

    def as_command(self) -> TranscriptCorrection:
        return TranscriptCorrection(self.turn_id, self.text)


class ClientPause(BaseModel):
    """ "Read it to me": hold the reading before the next paragraph."""

    type: Literal["pause"]


class ClientContinue(BaseModel):
    """ "Read it to me": go on after a pause, or now instead of waiting for an episode's drafts."""

    type: Literal["continue"]


class ClientMessage(BaseModel):
    """A JSON message from the client after the start message."""

    message: ClientEnd | ClientBeat | ClientCorrection | ClientPause | ClientContinue = Field(discriminator="type")


# ---- responses ----


class BoxOut(BaseModel):
    left: int
    top: int
    right: int
    bottom: int

    @classmethod
    def of(cls, b: Box) -> BoxOut:
        return cls(left=b.left, top=b.top, right=b.right, bottom=b.bottom)


class MaskOut(BaseModel):
    id: str
    label: str
    character_id: str | None
    box: BoxOut
    cutout_url: str | None

    @classmethod
    def of(cls, m: ObjectMask) -> MaskOut:
        return cls(
            id=m.id, label=m.label, character_id=m.character_id, box=BoxOut.of(m.box), cutout_url=media_url(m.cutout)
        )


class LayerOut(BaseModel):
    object_id: str
    dx: int
    dy: int
    scale: float
    deleted: bool

    @classmethod
    def of(cls, t: CanvasTransform) -> LayerOut:
        return cls(object_id=t.object_id, dx=t.dx, dy=t.dy, scale=t.scale, deleted=t.deleted)


class IssueOut(BaseModel):
    rule_id: str = Field(description="The rubric rule, e.g. CONT-04 (agents/*.md).")
    severity: Literal["blocker", "major", "minor"]
    description: str


class ProjectSettings(BaseModel):
    """Per-project settings. continuity_checks: the supervisor reviews every sheet and render (on by default)."""

    continuity_checks: bool


class ReviewOut(BaseModel):
    """The continuity supervisor's word on a panel or a reference sheet (ADR 0012)."""

    outcome: Literal["checked", "fixed", "needs_user", "accepted"]
    summary: str = Field(description='For the badge, e.g. "Fixed: remove the blue vest".')
    issues: list[IssueOut]
    fix_instruction: str = Field(description='The suggested appearance edit; "" when an edit cannot fix it.')
    model: str = Field(description="The model that checked it, e.g. muse-glimmer or muse-spark-1.3.")
    confidence: float
    fixes: int = Field(description="Automatic fixes applied before this verdict.")
    rubrics: dict[str, str] = Field(description="Rubric id -> hash of the rubric text the check used.")

    @classmethod
    def of(cls, outcome: Outcome, summary: str, v: Verdict, fixes: int = 0) -> ReviewOut:
        return cls(
            outcome=outcome.value,
            summary=summary,
            issues=[
                IssueOut(rule_id=i.rule_id, severity=i.severity.value, description=i.description) for i in v.issues
            ],
            fix_instruction=v.fix_instruction if v.can_fix else "",
            model=v.model,
            confidence=v.confidence,
            fixes=fixes,
            rubrics=dict(v.rubrics),
        )


class SupervisorEntryOut(BaseModel):
    at: str
    subject: str
    outcome: Literal["checked", "fixed", "needs_user", "accepted"]
    message: str
    rule_ids: list[str]
    model: str
    shot_id: str | None
    character_id: str | None

    @classmethod
    def of(cls, e: SupervisorEntry) -> SupervisorEntryOut:
        return cls(
            at=e.at,
            subject=e.subject,
            outcome=e.outcome.value,
            message=e.message,
            rule_ids=list(e.rule_ids),
            model=e.model,
            shot_id=e.shot_id,
            character_id=e.character_id,
        )


class PanelOut(BaseModel):
    revision: int = Field(description="The model render the masks and layers belong to.")
    shown_revision: int = Field(description="What image_url shows: the composite of the layers, or the render.")
    status: str
    image_url: str | None = Field(description="The panel as shown: with its layers applied once composited.")
    base_image_url: str | None = Field(description="The model render without layers; the editor draws on it.")
    width: int | None
    height: int | None
    masks: list[MaskOut]
    layers: list[LayerOut]
    outdated: bool = Field(description="The shot changed after this was drawn; draw it again.")
    review: ReviewOut | None = Field(default=None, description="The continuity check of this render, once done.")

    @classmethod
    def of(cls, p: Panel) -> PanelOut:
        size = p.shown_size
        return cls(
            revision=p.revision,
            shown_revision=p.current_revision,
            status=p.status.value,
            image_url=media_url(p.shown_image),
            base_image_url=media_url(p.image),
            width=size.width if size else None,
            height=size.height if size else None,
            masks=[MaskOut.of(m) for m in p.masks.values()],
            layers=[LayerOut.of(t) for t in p.transforms],
            outdated=p.outdated,
            review=ReviewOut.of(p.review.outcome, p.review.summary, p.review.verdict, p.review.fixes)
            if p.review and p.review.revision == p.revision
            else None,
        )


class ShotOut(BaseModel):
    id: str
    number: int
    framing: str
    character_ids: list[str]
    setting: str
    action: str
    dialogue: str
    duration_ms: int
    source_turn_ids: list[str]
    episode: int = Field(default=1, description="Shots are numbered through the story; the studio counts per episode.")
    panel: PanelOut | None = None
    looks: dict[str, str] = Field(
        default_factory=dict, description="Character id -> the look they wear in this shot, when not everyday."
    )

    @classmethod
    def of(cls, s: Shot, panel: Panel | None = None, looks: dict[str, str] | None = None) -> ShotOut:
        return cls(
            id=s.id,
            number=s.number,
            framing=s.framing.value,
            character_ids=list(s.character_ids),
            setting=s.setting,
            action=s.action,
            dialogue=s.dialogue,
            duration_ms=s.duration_ms,
            source_turn_ids=list(s.source_turn_ids),
            episode=s.episode,
            panel=PanelOut.of(panel) if panel else None,
            looks=looks or {},
        )


class LookOut(BaseModel):
    """Another outfit of a character (ADR 0018), with its own sheet."""

    id: str
    label: str
    clothes: str
    reference_url: str | None
    from_shots: list[int] = Field(description="The shots that show this look, in order.")
    sheet_error: str | None = Field(default=None, description="Why its sheet could not be drawn; offer Try again.")
    suggested_clothes: str | None = Field(
        default=None,
        description="Muse Image refused these clothes twice: offer this instead (Use this description); Try again "
        "with the same clothes answers 409 edit_first.",
    )


class CharacterOut(BaseModel):
    id: str
    name: str
    description: str
    reference_url: str | None
    review: ReviewOut | None = Field(default=None, description="The continuity check of this reference sheet.")
    sheet_error: str | None = Field(
        default=None, description="Why the last sheet could not be drawn, in plain words; offer Try again and Edit."
    )
    looks: list[LookOut] = Field(
        default_factory=list, description="Outfits besides the everyday one, each with its sheet."
    )
    suggested_description: str | None = Field(
        default=None,
        description="Muse Image refused this description twice: offer this instead (Use this description); Try "
        "again with the same description answers 409 edit_first.",
    )

    @classmethod
    def of(
        cls,
        c: Character,
        review: SheetReview | None = None,
        sheet_error: str | None = None,
        project: Project | None = None,
    ) -> CharacterOut:
        current = review if review and review.reference == c.reference else None
        looks = []
        for look in (project.shown(c) if project else c).looks:  # a look no shot shows is hidden
            worn = [s.number for s in project.shots if _wears(project, s, c.id, look.id)] if project else []
            failure = project.sheet_failures.get(sheet_target(c.id, look.id)) if project else None
            looks.append(
                LookOut(
                    id=look.id,
                    label=look.label,
                    clothes=look.clothes,
                    reference_url=media_url(look.reference),
                    from_shots=worn,
                    sheet_error=failure if look.reference is None else None,
                    suggested_clothes=_suggestion(project, sheet_target(c.id, look.id), look.clothes)
                    if look.reference is None
                    else None,
                )
            )
        return cls(
            id=c.id,
            name=c.name,
            description=c.canonical_description,
            reference_url=media_url(c.reference),
            review=ReviewOut.of(current.outcome, current.summary, current.verdict) if current else None,
            sheet_error=sheet_error if c.reference is None else None,
            looks=looks,
            suggested_description=_suggestion(project, c.id, c.canonical_description) if c.reference is None else None,
        )


def _suggestion(project: Project | None, target: str, text: str) -> str | None:
    """The suggestion for a refused sheet, while its text is still the one refused."""
    refusal = project.sheet_refusals.get(target) if project else None
    return refusal.suggestion if refusal and refusal.text == text else None


def _wears(project: Project, shot: Shot, character_id: str, look_id: str) -> bool:
    look = project.look_in(shot.id, character_id) if character_id in shot.character_ids else None
    return look is not None and look.id == look_id


def _shot_looks(project: Project, shot: Shot) -> dict[str, str]:
    return {c: look.id for c in shot.character_ids if (look := project.look_in(shot.id, c)) is not None}


class BeatMerge(BaseModel):
    other: Literal["previous", "next"] = Field(description="Which neighbouring beat to merge this one with.")


class CastOut(BaseModel):
    status: str
    characters: list[CharacterOut]


class TurnOut(BaseModel):
    id: str
    text: str
    start_ms: int
    end_ms: int
    speaker: str | None
    direction: str = Field(default="", description="From a script: the paragraph as written, with its cues.")
    episode: int = 1

    @classmethod
    def of(cls, t: TranscriptTurn) -> TurnOut:
        return cls(
            id=t.id,
            text=t.text,
            start_ms=t.start_ms,
            end_ms=t.end_ms,
            speaker=t.speaker,
            direction=t.direction,
            episode=t.episode,
        )


class NarrationOut(BaseModel):
    session: str
    duration_ms: int
    url: str
    voice: str | None = Field(default=None, description="The synthesized voice that read it; null: the user's own.")
    language: str | None = None


class AnimaticOut(BaseModel):
    url: str = Field(description="Plays inline; add ?download=1 to save it.")
    duration_ms: int
    subtitles: bool = Field(description="Captions are burned into the picture.")
    voiced: bool = Field(description="False when no narration was kept: the animatic is silent.")
    captions_url: str | None = Field(default=None, description="The captions as an .srt file (?download=1 saves it).")
    caption_language: str = Field(default="", description="The captions' locale when translated; empty: as spoken.")

    @classmethod
    def of(cls, a: AnimaticExport) -> AnimaticOut:
        return cls(
            url=f"/media/{a.video.key}",
            duration_ms=a.duration_ms,
            subtitles=a.subtitles,
            voiced=a.voiced,
            captions_url=f"/media/{a.captions.key}" if a.captions else None,
            caption_language=a.caption_language,
        )


class ProjectOut(BaseModel):
    id: str
    title: str
    style: Literal["pencil", "paper_cutout"]
    cast: CastOut
    turns: list[TurnOut]
    shots: list[ShotOut]
    narrations: list[NarrationOut] = Field(description="Kept recordings, one per live session, for the animatic.")
    animatic: AnimaticOut | None = Field(description="The latest exported animatic.")
    share_token: str | None = Field(description="The live share link's token: {api}/s/{token}. None when off.")
    share_public: bool = Field(description="Search engines may index the share page. Unlisted (noindex) when false.")
    continuity_checks: bool = Field(default=True, description="The continuity supervisor checks sheets and panels.")
    supervisor: list[SupervisorEntryOut] = Field(
        default_factory=list, description="The supervisor's decisions, oldest first (the last 100)."
    )

    @classmethod
    def of(cls, p: Project) -> ProjectOut:
        return cls(
            id=p.id,
            title=p.title,
            style=p.style.value,
            cast=CastOut(
                status=p.bible.status.value,
                characters=[
                    CharacterOut.of(c, p.sheet_reviews.get(c.id), p.sheet_failures.get(c.id), p)
                    for c in p.bible.characters.values()
                ],
            ),
            turns=[TurnOut.of(t) for t in p.turns],
            shots=[ShotOut.of(s, p.panels.get(s.id), _shot_looks(p, s)) for s in p.shots],
            narrations=[
                NarrationOut(
                    session=n.session,
                    duration_ms=n.duration_ms,
                    url=f"/media/{n.recording.key}",
                    voice=n.voice,
                    language=n.language,
                )
                for n in p.narrations.values()
            ],
            animatic=AnimaticOut.of(p.animatic) if p.animatic else None,
            share_token=p.share_token,
            share_public=p.share_public,
            continuity_checks=p.continuity_checks,
            supervisor=[SupervisorEntryOut.of(e) for e in p.supervisor_log],
        )


class ShareRequest(BaseModel):
    public: bool = Field(
        default=False, description="Let search engines index the share page. Off: the page is unlisted (noindex)."
    )


class ShareOut(BaseModel):
    token: str
    public: bool
    url: str = Field(description="The link to post: it previews on X and sends browsers to the share page.")
    page_url: str = Field(description="The read-only page in the studio.")


class SharedShotOut(BaseModel):
    number: int
    framing: str
    action: str
    dialogue: str
    duration_ms: int
    image_url: str | None


class SharedAnimaticOut(BaseModel):
    url: str
    duration_ms: int


def voice_name(voice: str) -> str:
    """ "en-US-BrandonMultilingualNeural" -> "Brandon"."""
    name = voice.split("-", 2)[-1]
    return name.removesuffix("Neural").removesuffix("Multilingual") or voice


class LanguageOut(BaseModel):
    code: str = Field(description='"fr"')
    locale: str = Field(description='"fr-FR": send it as the session\'s language.')
    name: str = Field(description="The language's own name.")


class VoiceOut(BaseModel):
    name: str
    display_name: str
    gender: str
    accent: str = Field(description='"en-US" or "en-GB".')
    languages: list[LanguageOut]
    preview_url: str = Field(description="Add ?language=fr-FR for another language.")

    @classmethod
    def of(cls, v: OfferedVoice) -> VoiceOut:
        return cls(
            name=v.name,
            display_name=v.display_name,
            gender=v.gender,
            accent=v.accent,
            languages=[LanguageOut(code=x.code, locale=x.locale, name=x.name) for x in v.languages],
            preview_url=f"/voices/{v.name}/preview",
        )


class VoicesOut(BaseModel):
    available: bool = Field(description='False when Text-to-Speech is not set up: hide "Read it to me".')
    default: str
    voices: list[VoiceOut]


class SharedProjectOut(BaseModel):
    """What a share link shows: read-only, with media under /shares/{token}/, never the project id."""

    title: str
    style: Literal["pencil", "paper_cutout"]
    shots: list[SharedShotOut]
    animatic: SharedAnimaticOut | None
    public: bool = Field(description="Indexable by search engines; otherwise the page must say noindex.")
    narrated_by: str | None = Field(
        default=None, description='The synthesized voice that narrated it ("Brandon"); null: the author\'s own voice.'
    )
    creator: CreatorOut | None = Field(
        default=None, description="How its gallery entry is signed; null when it is not in the gallery."
    )

    @classmethod
    def of(cls, p: Project, token: str, creator: Creator | None = None) -> SharedProjectOut:
        base = f"/shares/{token}"
        shots = []
        for s in p.shots:
            panel = p.panels.get(s.id)
            drawn = panel is not None and panel.shown_image is not None and panel.status.value == "ready"
            shots.append(
                SharedShotOut(
                    number=s.number,
                    framing=s.framing.value,
                    action=s.action,
                    dialogue=s.dialogue,
                    duration_ms=s.duration_ms,
                    image_url=f"{base}/panels/{s.number}" if drawn else None,
                )
            )
        animatic = SharedAnimaticOut(url=f"{base}/animatic", duration_ms=p.animatic.duration_ms) if p.animatic else None
        voices = [n.voice for n in p.narrations.values() if n.voice]
        return cls(
            title=p.title,
            style=p.style.value,
            shots=shots,
            animatic=animatic,
            public=p.share_public,
            narrated_by=voice_name(voices[-1]) if voices else None,
            creator=CreatorOut.of(creator) if creator is not None else None,
        )


class CastReviewOut(BaseModel):
    approved: bool
    redrawing: list[str]
    job_key: str | None

    @classmethod
    def of(cls, r: CastReview) -> CastReviewOut:
        return cls(approved=r.approved, redrawing=list(r.redrawing), job_key=r.job_key)


class LimitsOut(BaseModel):
    projects_per_visitor_per_day: int
    narration_minutes_per_session: float
    shots_per_episode: int
    episodes_per_script: int
    script_characters: int
    renders_per_project: int
    exports_per_project: int


class StudioStatusOut(BaseModel):
    """Whether the studio takes new work: the studio checks this before starting a story."""

    paused: bool = Field(description="The kill switch is on: show the back-soon page (shared storyboards still open).")
    full: bool = Field(description="Today's spend cap is reached: no new work until midnight UTC+4.")
    judge: bool = Field(default=False, description="This browser has a valid judge pass (show the badge).")
    limits: LimitsOut

    @classmethod
    def of(cls, s: StudioStatus) -> StudioStatusOut:
        return cls(
            paused=s.paused,
            full=s.full,
            judge=s.judge,
            limits=LimitsOut(
                projects_per_visitor_per_day=s.limits.projects_per_visitor_per_day,
                narration_minutes_per_session=s.limits.narration_ms_per_session / 60_000,
                shots_per_episode=s.limits.shots_per_episode,
                episodes_per_script=s.limits.episodes_per_script,
                script_characters=s.limits.script_characters,
                renders_per_project=s.limits.renders_per_project,
                exports_per_project=s.limits.exports_per_project,
            ),
        )


class JobStatusOut(BaseModel):
    """A job's status, as the fallback when job.updated events were missed (a dropped socket, a new revision)."""

    key: str
    status: Literal["queued", "running", "succeeded", "failed", "unknown"] = Field(
        description="unknown: this server never saw the job, e.g. it started on a revision that has since been "
        "replaced. Fetch the project to see whether its result arrived."
    )
    message: str | None = Field(default=None, description="User-facing, on failure.")


class TicketOut(BaseModel):
    """A queued job. Follow it with job.updated events on the session WebSocket, or poll the project."""

    kind: str
    key: str
    enqueued: bool
    shot_id: str | None
    revision: int | None

    @classmethod
    def of(cls, t: JobTicket) -> TicketOut:
        return cls(kind=t.kind, key=t.key, enqueued=t.enqueued, shot_id=t.shot_id, revision=t.revision)


class SelectionOut(BaseModel):
    cached: bool
    mask: MaskOut

    @classmethod
    def of(cls, s: Selection) -> SelectionOut:
        return cls(cached=s.cached, mask=MaskOut.of(s.mask))


class DictationOut(BaseModel):
    """What was said, for the user to check before it is sent as an edit."""

    text: str


class ShotsOut(BaseModel):
    shots: list[ShotOut]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorOut(BaseModel):
    error: ErrorBody


# ---- WebSocket events (documented in docs/api-events.md) ----


def event_message(event: ProjectEvent) -> dict[str, Any]:
    """The JSON a WebSocket client receives for a project event."""
    match event:
        case TranscriptUpdated(text):
            return {"type": "transcript.partial", "text": text}
        case TurnFinished(turn):
            return {"type": "turn.completed", "turn": TurnOut.of(turn).model_dump()}
        case ShotCreated(shot, looks):
            return {"type": "shot.created", "shot": ShotOut.of(shot, looks=dict(looks)).model_dump()}
        case ShotUpdated(shot, looks):
            return {"type": "shot.updated", "shot": ShotOut.of(shot, looks=dict(looks)).model_dump()}
        case ShotsReplaced(turn, removed, shots):
            return {
                "type": "shots.replaced",
                "turn": TurnOut.of(turn).model_dump(),
                "removed_shot_ids": list(removed),
                "shots": [ShotOut.of(s).model_dump() for s in shots],
            }
        case CastProposed(characters):
            return {"type": "cast.proposed", "characters": [CharacterOut.of(c).model_dump() for c in characters]}
        case JobUpdated(kind, key, status, shot_id, revision, message, progress, position, estimate_s):
            return {
                "type": "job.updated",
                "kind": kind,
                "key": key,
                "status": status,
                "shot_id": shot_id,
                "revision": revision,
                "message": message,
                "progress": progress,
                "position": position,
                "estimate_s": estimate_s,
            }
        case SessionFailed(message, fatal):
            return error_message(message, fatal=fatal)
        case NoSpeechHeard(after_ms, level):
            return {"type": "audio.silent", "after_ms": after_ms, "level": level}
        case SessionEnded(turns, shots, heard):
            return {"type": "session.ended", "turns": turns, "shots": shots, "heard": heard}
        case SupervisorReviewed(entry, revision):
            return {
                "type": "supervisor.reviewed",
                "entry": SupervisorEntryOut.of(entry).model_dump(),
                "revision": revision,
            }
        case SupervisorFixed(entry, revision, fixes):
            return {
                "type": "supervisor.fixed",
                "entry": SupervisorEntryOut.of(entry).model_dump(),
                "revision": revision,
                "fixes": fixes,
            }
        case SupervisorNeedsUser(entry, issues, fix_instruction, revision):
            return {
                "type": "supervisor.needs_user",
                "entry": SupervisorEntryOut.of(entry).model_dump(),
                "issues": [
                    IssueOut(rule_id=i.rule_id, severity=i.severity.value, description=i.description).model_dump()
                    for i in issues
                ],
                "fix_instruction": fix_instruction,
                "revision": revision,
            }
        case ScriptAccepted(script):
            return script_message(script)
        case TeleprompterAdvanced(paragraph):
            return {"type": "teleprompter.advanced", "paragraph": paragraph}
        case ParagraphVoiced(paragraph, episode, text, original, audio, duration_ms):
            return {
                "type": "script.voiced",
                "paragraph": paragraph,
                "episode": episode,
                "text": text,
                "original": original,
                "audio_url": f"/media/{audio.key}",
                "duration_ms": duration_ms,
            }
        case ReadingPaused(next_paragraph, next_episode, reason):
            return {
                "type": "script.paused",
                "next_paragraph": next_paragraph,
                "next_episode": next_episode,
                "reason": reason,
            }
        case ReadingResumed(next_paragraph):
            return {"type": "script.resumed", "next_paragraph": next_paragraph}


def script_message(script: Script) -> dict[str, Any]:
    return {
        "type": "script.accepted",
        "episodes": [
            {
                "number": e.number,
                "paragraphs": [{"narration": b.narration, "direction": b.direction} for b in e.beats],
            }
            for e in script.episodes
        ],
    }


def error_message(message: str, *, fatal: bool = False) -> dict[str, Any]:
    return {"type": "error", "message": message, "fatal": fatal}


# ---- "Report a problem" ----


class ProblemReportIn(BaseModel):
    text: str = Field(default="", max_length=500, description="What went wrong, in the visitor's words. Optional.")


class ProblemReportedOut(BaseModel):
    id: str


# ---- the gallery (ADR 0017) ----


class CreatorOut(BaseModel):
    """How the creator signed their entry. Empty strings: left out (both empty: an anonymous storyteller)."""

    name: str = Field(description="A display name or nickname, at most 40 characters; not necessarily a real name.")
    country: str = Field(description="ISO 3166-1 alpha-2 code, or empty.")
    official: bool = Field(
        default=False, description='Signed or published by the admin with a reserved name: show an "Official" badge.'
    )

    @classmethod
    def of(cls, c: Creator) -> CreatorOut:
        return cls(name=c.name, country=c.country, official=c.official)


class GallerySignRequest(BaseModel):
    """The creator's optional signature. Empty or null leaves a field out (or removes it, on an edit)."""

    name: str | None = Field(default=None, max_length=MAX_NAME_CHARS * 2, description="At most 40 characters.")
    country: str | None = Field(
        default=None, max_length=2, description="ISO 3166-1 alpha-2, only when the creator chose or confirmed it."
    )


class GallerySubmitRequest(GallerySignRequest):
    consent: bool = Field(description="The creator agreed to show this storyboard publicly in the gallery.")
    audio: GalleryAudio = Field(
        default="mine", description='"mine": the kept narration; "voice": the Ava voice instead; "none": silent.'
    )


class MyGalleryEntryOut(BaseModel):
    """The creator's view of their entry."""

    id: str
    status: Literal["checking", "published", "pending", "hidden", "failed"]
    note: str = Field(description="Why it is waiting, hidden or failed, in plain words.")
    audio: GalleryAudio
    hearts: int
    featured: bool
    submitted_at: datetime
    creator: CreatorOut

    @classmethod
    def of(cls, e: GalleryEntry) -> MyGalleryEntryOut:
        note = e.note if e.status in (EntryStatus.FAILED, EntryStatus.PENDING) else ""
        if e.status is EntryStatus.PENDING:
            note = "A person will look at it before it appears in the gallery."  # never the reviewer's own words
            if e.note == RESERVED_NOTE:  # our own rule, not a review: say which part to change
                note = "That name is reserved for official Frameteller entries, so a person will look at it first."
        return cls(
            id=e.id,
            status=e.status.value,
            note=note,
            audio=e.audio,
            hearts=len(e.hearts),
            featured=e.featured,
            submitted_at=e.submitted_at,
            creator=CreatorOut.of(e.creator),
        )


class GalleryCardOut(BaseModel):
    id: str
    title: str
    style: str
    episodes: int
    shots: int
    duration_ms: int
    cover_url: str
    video_url: str
    share_url: str = Field(description="The storyboard's share page.")
    hearts: int
    hearted: bool = Field(description="This browser already gave it a heart.")
    featured: bool
    published_at: datetime | None
    creator: CreatorOut

    @classmethod
    def of(cls, e: GalleryEntry, app_url: str, browser: str) -> GalleryCardOut:
        return cls(
            id=e.id,
            title=e.title,
            style=e.style,
            episodes=e.episodes,
            shots=e.shots,
            duration_ms=e.duration_ms,
            cover_url=f"/gallery/{e.id}/cover.webp",
            video_url=f"/gallery/{e.id}/video.mp4",
            share_url=f"{app_url}/s/{e.share_token}",
            hearts=len(e.hearts),
            hearted=browser in e.hearts,
            featured=e.featured,
            published_at=e.published_at,
            creator=CreatorOut.of(e.creator),
        )


class GalleryCountryOut(BaseModel):
    code: str = Field(description="ISO 3166-1 alpha-2.")
    entries: int


class GalleryPageOut(BaseModel):
    entries: list[GalleryCardOut]
    countries: list[GalleryCountryOut] = Field(
        default_factory=list,
        description="Creator countries across the whole gallery, most entries first: the counter and the filter.",
    )


class CountriesOut(BaseModel):
    codes: list[str] = Field(description="Every ISO 3166-1 alpha-2 code a creator may choose.")
    suggested: str | None = Field(
        description="A guess from the request (its language region), to offer only: never publish it unconfirmed."
    )


class HeartOut(BaseModel):
    hearts: int
    hearted: bool


class GalleryReportRequest(BaseModel):
    reason: str = Field(default="", max_length=MAX_REPORT_CHARS)


class GalleryReportOut(BaseModel):
    reason: str
    at: datetime


class AdminGalleryEntryOut(BaseModel):
    id: str
    project_id: str
    title: str
    style: str
    status: str
    note: str
    reviewed_by: str
    audio: str
    featured: bool
    hearts: int
    reports: list[GalleryReportOut]
    submitted_at: datetime
    published_at: datetime | None
    share_token: str
    has_video: bool
    creator: CreatorOut

    @classmethod
    def of(cls, e: GalleryEntry) -> AdminGalleryEntryOut:
        return cls(
            id=e.id,
            project_id=e.project_id,
            title=e.title,
            style=e.style,
            status=e.status.value,
            note=e.note,
            reviewed_by=e.reviewed_by,
            audio=e.audio,
            featured=e.featured,
            hearts=len(e.hearts),
            reports=[GalleryReportOut(reason=r.reason, at=r.at) for r in e.reports],
            submitted_at=e.submitted_at,
            published_at=e.published_at,
            share_token=e.share_token,
            has_video=e.video is not None,
            creator=CreatorOut.of(e.creator),
        )


class AdminGalleryAction(BaseModel):
    action: Literal["publish", "hide", "feature", "unfeature"]
