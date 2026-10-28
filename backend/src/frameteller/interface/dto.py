"""Request and response DTOs. Separate from domain entities: the API can change shape without touching rules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from frameteller.application.events import (
    CastProposed,
    JobUpdated,
    NoSpeechHeard,
    ProjectEvent,
    SessionEnded,
    SessionFailed,
    ShotCreated,
    ShotsReplaced,
    ShotUpdated,
    TranscriptUpdated,
    TurnFinished,
)
from frameteller.application.ports import Quality, SpeechMode, SpeechOptions
from frameteller.application.use_cases import Beat, CastReview, JobTicket, Selection, TranscriptCorrection
from frameteller.application.use_cases.correct_transcript import MAX_TURN_CHARS
from frameteller.domain import (
    AnimaticExport,
    Box,
    CanvasTransform,
    Character,
    MediaRef,
    ObjectMask,
    Panel,
    PanelStyle,
    Project,
    Shot,
    TranscriptTurn,
)

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
    subtitles: bool = Field(default=False, description="Burn the narration's words into the picture.")


class ReorderRequest(BaseModel):
    shot_ids: list[str] = Field(min_length=1, max_length=500)


class SessionStart(BaseModel):
    """First WebSocket message. Mode and keywords are fixed for the session (CLAUDE.md section 5)."""

    mode: Literal["narrate", "co_direct"] = "narrate"
    keywords: list[str] = Field(default_factory=list, max_length=50)
    keep_audio: bool = Field(default=False, description="The narrator agreed to keep the recording for the animatic.")

    def as_options(self) -> SpeechOptions:
        mode = SpeechMode.CO_DIRECTION if self.mode == "co_direct" else SpeechMode.NARRATION
        keywords = tuple(dict.fromkeys(k.strip()[:40] for k in self.keywords if k.strip()))
        return SpeechOptions(mode=mode, keywords=keywords)


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


class ClientMessage(BaseModel):
    """A JSON message from the client after the start message."""

    message: ClientEnd | ClientBeat | ClientCorrection = Field(discriminator="type")


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
    panel: PanelOut | None = None

    @classmethod
    def of(cls, s: Shot, panel: Panel | None = None) -> ShotOut:
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
            panel=PanelOut.of(panel) if panel else None,
        )


class CharacterOut(BaseModel):
    id: str
    name: str
    description: str
    reference_url: str | None

    @classmethod
    def of(cls, c: Character) -> CharacterOut:
        return cls(id=c.id, name=c.name, description=c.canonical_description, reference_url=media_url(c.reference))


class CastOut(BaseModel):
    status: str
    characters: list[CharacterOut]


class TurnOut(BaseModel):
    id: str
    text: str
    start_ms: int
    end_ms: int
    speaker: str | None

    @classmethod
    def of(cls, t: TranscriptTurn) -> TurnOut:
        return cls(id=t.id, text=t.text, start_ms=t.start_ms, end_ms=t.end_ms, speaker=t.speaker)


class NarrationOut(BaseModel):
    session: str
    duration_ms: int
    url: str


class AnimaticOut(BaseModel):
    url: str = Field(description="Plays inline; add ?download=1 to save it.")
    duration_ms: int
    subtitles: bool
    voiced: bool = Field(description="False when no narration was kept: the animatic is silent.")

    @classmethod
    def of(cls, a: AnimaticExport) -> AnimaticOut:
        return cls(url=f"/media/{a.video.key}", duration_ms=a.duration_ms, subtitles=a.subtitles, voiced=a.voiced)


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

    @classmethod
    def of(cls, p: Project) -> ProjectOut:
        return cls(
            id=p.id,
            title=p.title,
            style=p.style.value,
            cast=CastOut(
                status=p.bible.status.value, characters=[CharacterOut.of(c) for c in p.bible.characters.values()]
            ),
            turns=[TurnOut.of(t) for t in p.turns],
            shots=[ShotOut.of(s, p.panels.get(s.id)) for s in p.shots],
            narrations=[
                NarrationOut(session=n.session, duration_ms=n.duration_ms, url=f"/media/{n.recording.key}")
                for n in p.narrations.values()
            ],
            animatic=AnimaticOut.of(p.animatic) if p.animatic else None,
            share_token=p.share_token,
        )


class ShareOut(BaseModel):
    token: str
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


class SharedProjectOut(BaseModel):
    """What a share link shows: read-only, with media under /shares/{token}/, never the project id."""

    title: str
    style: Literal["pencil", "paper_cutout"]
    shots: list[SharedShotOut]
    animatic: SharedAnimaticOut | None

    @classmethod
    def of(cls, p: Project, token: str) -> SharedProjectOut:
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
        return cls(title=p.title, style=p.style.value, shots=shots, animatic=animatic)


class CastReviewOut(BaseModel):
    approved: bool
    redrawing: list[str]
    job_key: str | None

    @classmethod
    def of(cls, r: CastReview) -> CastReviewOut:
        return cls(approved=r.approved, redrawing=list(r.redrawing), job_key=r.job_key)


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
        case ShotCreated(shot):
            return {"type": "shot.created", "shot": ShotOut.of(shot).model_dump()}
        case ShotUpdated(shot):
            return {"type": "shot.updated", "shot": ShotOut.of(shot).model_dump()}
        case ShotsReplaced(turn, removed, shots):
            return {
                "type": "shots.replaced",
                "turn": TurnOut.of(turn).model_dump(),
                "removed_shot_ids": list(removed),
                "shots": [ShotOut.of(s).model_dump() for s in shots],
            }
        case CastProposed(characters):
            return {"type": "cast.proposed", "characters": [CharacterOut.of(c).model_dump() for c in characters]}
        case JobUpdated(kind, key, status, shot_id, revision, message, progress):
            return {
                "type": "job.updated",
                "kind": kind,
                "key": key,
                "status": status,
                "shot_id": shot_id,
                "revision": revision,
                "message": message,
                "progress": progress,
            }
        case SessionFailed(message, fatal):
            return error_message(message, fatal=fatal)
        case NoSpeechHeard(after_ms, level):
            return {"type": "audio.silent", "after_ms": after_ms, "level": level}
        case SessionEnded(turns, shots, heard):
            return {"type": "session.ended", "turns": turns, "shots": shots, "heard": heard}


def error_message(message: str, *, fatal: bool = False) -> dict[str, Any]:
    return {"type": "error", "message": message, "fatal": fatal}
