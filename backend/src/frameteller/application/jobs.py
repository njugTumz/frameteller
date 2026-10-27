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


def panel_key(kind: str, project_id: str, shot_id: str, revision: int) -> str:
    return f"{kind}:{project_id}:{shot_id}:r{revision}"


def pre_segment_job(project_id: str, shot_id: str, revision: int) -> Job:
    return Job(
        kind=PRE_SEGMENT_PANEL,
        idempotency_key=panel_key(PRE_SEGMENT_PANEL, project_id, shot_id, revision),
        payload={"project_id": project_id, "shot_id": shot_id, "revision": str(revision)},
    )


def panel_job(project_id: str, shot_id: str, revision: int, quality: Quality) -> Job:
    return Job(
        kind=GENERATE_PANEL,
        idempotency_key=panel_key(GENERATE_PANEL, project_id, shot_id, revision),
        payload={"project_id": project_id, "shot_id": shot_id, "revision": str(revision), "quality": quality},
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


def cast_job(project_id: str, character_ids: Sequence[str], nonce: str) -> Job:
    """Reference sheets for some characters. `nonce` separates a deliberate regenerate from a retry."""
    ids = sorted(set(character_ids))
    return Job(
        kind=GENERATE_CAST,
        idempotency_key=f"{GENERATE_CAST}:{project_id}:{','.join(ids)}:{nonce}",
        payload={"project_id": project_id, "character_ids": ",".join(ids)},
    )
