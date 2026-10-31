"""Job kinds and idempotency keys. A key is project + shot + revision, so retries never double-charge."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from frameteller.application.ports import Job, Quality

GENERATE_PANEL = "generate_panel"
PRE_SEGMENT_PANEL = "pre_segment_panel"
EDIT_PANEL = "edit_panel"
GENERATE_CAST = "generate_cast"
EXPORT_ANIMATIC = "export_animatic"
COMPOSE_PANEL = "compose_panel"
SUPERVISE_PANEL = "supervise_panel"
REVIEW_SHEET = "review_sheet"
GALLERY_SUBMISSION = "gallery_submission"


def panel_key(kind: str, project_id: str, shot_id: str, revision: int) -> str:
    return f"{kind}:{project_id}:{shot_id}:r{revision}"


def pre_segment_job(project_id: str, shot_id: str, revision: int) -> Job:
    return Job(
        kind=PRE_SEGMENT_PANEL,
        idempotency_key=panel_key(PRE_SEGMENT_PANEL, project_id, shot_id, revision),
        payload={"project_id": project_id, "shot_id": shot_id, "revision": str(revision)},
    )


def panel_job(
    project_id: str, shot_id: str, revision: int, quality: Quality, redraw: str = "", change: str = ""
) -> Job:
    """`redraw` is "" (a first drawing or Draw final), "new" or "surprise"; `change` is what should change."""
    payload = {"project_id": project_id, "shot_id": shot_id, "revision": str(revision), "quality": quality}
    if redraw:
        payload |= {"redraw": redraw, "change": change}
    return Job(
        kind=GENERATE_PANEL, idempotency_key=panel_key(GENERATE_PANEL, project_id, shot_id, revision), payload=payload
    )


def edit_job(project_id: str, shot_id: str, base_revision: int, instruction: str) -> Job:
    """Keyed on the revision it edits and the instruction, so a double-submitted edit runs once."""
    digest = hashlib.sha256(instruction.strip().lower().encode()).hexdigest()[:12]
    return Job(
        kind=EDIT_PANEL,
        idempotency_key=panel_key(EDIT_PANEL, project_id, shot_id, base_revision) + f":{digest}",
        payload={
            "project_id": project_id,
            "shot_id": shot_id,
            "revision": str(base_revision),
            "instruction": instruction,
        },
    )


def compose_job(project_id: str, shot_id: str, base_revision: int, layers: str) -> Job:
    """Apply the geometry layers to a base render. Keyed on the layers, so the same arrangement composes once."""
    digest = hashlib.sha256(layers.encode()).hexdigest()[:12]
    return Job(
        kind=COMPOSE_PANEL,
        idempotency_key=panel_key(COMPOSE_PANEL, project_id, shot_id, base_revision) + f":{digest}",
        payload={"project_id": project_id, "shot_id": shot_id, "revision": str(base_revision)},
    )


def export_job(project_id: str, digest: str, options: dict[str, str]) -> Job:
    """Render the animatic. Keyed on what it shows, so an unchanged storyboard exports once."""
    key = f"{EXPORT_ANIMATIC}:{project_id}:{digest}"
    return Job(
        kind=EXPORT_ANIMATIC,
        idempotency_key=key,
        payload={"project_id": project_id, **options, "job_key": key},  # the key, for progress events
    )


def supervise_job(project_id: str, shot_id: str, revision: int, quality: Quality) -> Job:
    """Review a new render (and fix a draft if it can). One review per revision."""
    return Job(
        kind=SUPERVISE_PANEL,
        idempotency_key=panel_key(SUPERVISE_PANEL, project_id, shot_id, revision),
        payload={"project_id": project_id, "shot_id": shot_id, "revision": str(revision), "quality": quality},
    )


def sheet_review_job(project_id: str, character_id: str, reference_key: str) -> Job:
    """Review a new reference sheet. Keyed on the sheet itself, so each drawing is reviewed once."""
    digest = hashlib.sha256(reference_key.encode()).hexdigest()[:12]
    return Job(
        kind=REVIEW_SHEET,
        idempotency_key=f"{REVIEW_SHEET}:{project_id}:{character_id}:{digest}",
        payload={"project_id": project_id, "character_id": character_id, "reference": reference_key},
    )


def cast_job(project_id: str, character_ids: Sequence[str], nonce: str, correction: str = "") -> Job:
    """Reference sheets for some characters. `nonce` separates a deliberate regenerate from a retry."""
    ids = sorted(set(character_ids))
    return Job(
        kind=GENERATE_CAST,
        idempotency_key=f"{GENERATE_CAST}:{project_id}:{','.join(ids)}:{nonce}",
        payload={"project_id": project_id, "character_ids": ",".join(ids), "correction": correction},
    )


def gallery_job(project_id: str, entry_id: str, check: int = 0) -> Job:
    """Render the gallery copy and run the moderation review. One per submission, and one per later check of a
    new creator name (`check`), which reviews again without rendering again."""
    suffix = f":{check}" if check else ""
    return Job(
        kind=GALLERY_SUBMISSION,
        idempotency_key=f"{GALLERY_SUBMISSION}:{project_id}:{entry_id}{suffix}",
        payload={"project_id": project_id, "entry_id": entry_id},
    )
