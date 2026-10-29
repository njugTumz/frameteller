"""Project <-> JSON. Explicit mapping keeps the domain free of persistence concerns."""

from __future__ import annotations

import base64
import zlib
from typing import Any

from frameteller.domain import (
    AnimaticExport,
    Box,
    CanvasTransform,
    CastStatus,
    Character,
    CharacterBible,
    CleanPlate,
    Composite,
    Decision,
    Framing,
    Issue,
    MaskBitmap,
    MediaRef,
    Narration,
    ObjectMask,
    Outcome,
    Panel,
    PanelReview,
    PanelStatus,
    PanelStyle,
    Project,
    Severity,
    SheetReview,
    Shot,
    Size,
    SupervisorEntry,
    TranscriptTurn,
    Verdict,
)

SCHEMA_VERSION = 1


def _ref(r: MediaRef | None) -> str | None:
    return r.key if r else None


def _unref(k: str | None) -> MediaRef | None:
    return MediaRef(k) if k else None


def _box(b: Box) -> list[int]:
    return [b.left, b.top, b.right, b.bottom]


def _mask(m: ObjectMask) -> dict[str, Any]:
    return {
        "id": m.id,
        "label": m.label,
        "box": _box(m.box),
        # 0/1 rasters compress very well
        "bitmap": base64.b64encode(zlib.compress(m.bitmap.data, 6)).decode(),
        "cutout": _ref(m.cutout),
        "character_id": m.character_id,
    }


def _unmask(d: dict[str, Any]) -> ObjectMask:
    box = Box(*d["box"])
    return ObjectMask(
        d["id"],
        d["label"],
        MaskBitmap(box, zlib.decompress(base64.b64decode(d["bitmap"]))),
        cutout=_unref(d["cutout"]),
        character_id=d["character_id"],
    )


def project_to_dict(p: Project) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "id": p.id,
        "title": p.title,
        "style": p.style.value,
        "cast_status": p.bible.status.value,
        "characters": [
            {"id": c.id, "name": c.name, "description": c.canonical_description, "reference": _ref(c.reference)}
            for c in p.bible.characters.values()
        ],
        "turns": [
            {"id": t.id, "text": t.text, "start_ms": t.start_ms, "end_ms": t.end_ms, "speaker": t.speaker}
            for t in p.turns
        ],
        "shots": [
            {
                "id": s.id,
                "number": s.number,
                "framing": s.framing.value,
                "character_ids": list(s.character_ids),
                "setting": s.setting,
                "action": s.action,
                "dialogue": s.dialogue,
                "source_turn_ids": list(s.source_turn_ids),
                "duration_ms": s.duration_ms,
            }
            for s in p.shots
        ],
        "panels": [
            {
                "shot_id": pn.shot_id,
                "revision": pn.revision,
                "status": pn.status.value,
                "image": _ref(pn.image),
                "response_id": pn.response_id,
                "size": [pn.size.width, pn.size.height] if pn.size else None,
                "masks": [_mask(m) for m in pn.masks.values()],
                "transforms": [
                    {"object_id": t.object_id, "dx": t.dx, "dy": t.dy, "scale": t.scale, "deleted": t.deleted}
                    for t in pn.transforms
                ],
                "outdated": pn.outdated,
                "plates": [
                    {"object_ids": list(pl.object_ids), "image": pl.image.key, "response_id": pl.response_id}
                    for pl in pn.plates.values()
                ],
                "composite": (
                    {
                        "revision": pn.composite.revision,
                        "image": pn.composite.image.key,
                        "size": [pn.composite.size.width, pn.composite.size.height],
                    }
                    if pn.composite
                    else None
                ),
                "review": _panel_review(pn.review) if pn.review else None,
            }
            for pn in p.panels.values()
        ],
        "narrations": [
            {"session": n.session, "recording": n.recording.key, "duration_ms": n.duration_ms}
            for n in p.narrations.values()
        ],
        "share_token": p.share_token,
        "share_public": p.share_public,
        "usage": dict(p.usage),
        "continuity_checks": p.continuity_checks,
        "sheet_reviews": {
            cid: {
                "reference": r.reference.key,
                "outcome": r.outcome.value,
                "verdict": _verdict(r.verdict),
                "summary": r.summary,
            }
            for cid, r in p.sheet_reviews.items()
        },
        "supervisor_log": [
            {
                "at": e.at,
                "subject": e.subject,
                "outcome": e.outcome.value,
                "message": e.message,
                "rule_ids": list(e.rule_ids),
                "model": e.model,
                "shot_id": e.shot_id,
                "character_id": e.character_id,
            }
            for e in p.supervisor_log
        ],
        "animatic": (
            {
                "video": p.animatic.video.key,
                "duration_ms": p.animatic.duration_ms,
                "subtitles": p.animatic.subtitles,
                "voiced": p.animatic.voiced,
            }
            if p.animatic
            else None
        ),
    }


def _verdict(v: Verdict) -> dict[str, Any]:
    return {
        "decision": v.decision.value,
        "confidence": v.confidence,
        "issues": [
            {"rule_id": i.rule_id, "severity": i.severity.value, "description": i.description} for i in v.issues
        ],
        "fix_instruction": v.fix_instruction,
        "fix_target": v.fix_target,
        "fix_parts": list(v.fix_parts),
        "model": v.model,
        "latency_ms": v.latency_ms,
        "rubrics": [list(r) for r in v.rubrics],
    }


def _unverdict(d: dict[str, Any]) -> Verdict:
    return Verdict(
        Decision(d["decision"]),
        float(d["confidence"]),
        tuple(Issue(i["rule_id"], Severity(i["severity"]), i["description"]) for i in d["issues"]),
        d["fix_instruction"],
        d["fix_target"],
        tuple(d["fix_parts"]),
        d["model"],
        int(d["latency_ms"]),
        tuple((r[0], r[1]) for r in d["rubrics"]),
    )


def _panel_review(r: PanelReview) -> dict[str, Any]:
    return {
        "revision": r.revision,
        "outcome": r.outcome.value,
        "verdict": _verdict(r.verdict),
        "fixes": r.fixes,
        "summary": r.summary,
    }


def _unpanel_review(d: dict[str, Any] | None) -> PanelReview | None:
    if not d:
        return None
    return PanelReview(d["revision"], Outcome(d["outcome"]), _unverdict(d["verdict"]), d["fixes"], d["summary"])


def _composite(d: dict[str, Any] | None) -> Composite | None:
    return Composite(d["revision"], MediaRef(d["image"]), Size(*d["size"])) if d else None


def project_from_dict(d: dict[str, Any]) -> Project:
    if d.get("schema") != SCHEMA_VERSION:
        raise ValueError(f"unsupported project schema {d.get('schema')!r}")
    bible = CharacterBible(
        {c["id"]: Character(c["id"], c["name"], c["description"], _unref(c["reference"])) for c in d["characters"]},
        CastStatus(d["cast_status"]),
    )
    panels = {}
    for pd in d["panels"]:
        panels[pd["shot_id"]] = Panel(
            shot_id=pd["shot_id"],
            revision=pd["revision"],
            status=PanelStatus(pd["status"]),
            image=_unref(pd["image"]),
            response_id=pd["response_id"],
            size=Size(*pd["size"]) if pd["size"] else None,
            masks={m["id"]: _unmask(m) for m in pd["masks"]},
            transforms=[CanvasTransform(**t) for t in pd["transforms"]],
            outdated=pd.get("outdated", False),
            plates={
                plate.key: plate
                for plate in (
                    CleanPlate(tuple(pl["object_ids"]), MediaRef(pl["image"]), pl["response_id"])
                    for pl in pd.get("plates", [])
                )
            },
            composite=_composite(pd.get("composite")),
            review=_unpanel_review(pd.get("review")),
        )
    return Project(
        id=d["id"],
        title=d["title"],
        style=PanelStyle(d.get("style", PanelStyle.PENCIL.value)),  # projects saved before styles are pencil
        bible=bible,
        turns=[TranscriptTurn(t["id"], t["text"], t["start_ms"], t["end_ms"], t["speaker"]) for t in d["turns"]],
        shots=[
            Shot(
                s["id"],
                s["number"],
                Framing(s["framing"]),
                tuple(s["character_ids"]),
                s["setting"],
                s["action"],
                s["dialogue"],
                tuple(s["source_turn_ids"]),
                s["duration_ms"],
            )
            for s in d["shots"]
        ],
        panels=panels,
        narrations={
            n["session"]: Narration(n["session"], MediaRef(n["recording"]), n["duration_ms"])
            for n in d.get("narrations", [])
        },
        animatic=_animatic(d.get("animatic")),
        share_token=d.get("share_token"),
        share_public=bool(d.get("share_public", False)),
        usage={str(k): int(v) for k, v in d.get("usage", {}).items()},
        continuity_checks=bool(d.get("continuity_checks", True)),
        sheet_reviews={
            cid: SheetReview(MediaRef(r["reference"]), Outcome(r["outcome"]), _unverdict(r["verdict"]), r["summary"])
            for cid, r in d.get("sheet_reviews", {}).items()
        },
        supervisor_log=[
            SupervisorEntry(
                e["at"],
                e["subject"],
                Outcome(e["outcome"]),
                e["message"],
                tuple(e["rule_ids"]),
                e["model"],
                e["shot_id"],
                e["character_id"],
            )
            for e in d.get("supervisor_log", [])
        ],
    )


def _animatic(d: dict[str, Any] | None) -> AnimaticExport | None:
    return AnimaticExport(MediaRef(d["video"]), d["duration_ms"], d["subtitles"], d["voiced"]) if d else None
