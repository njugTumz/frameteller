"""Job kinds and idempotency keys. A key is project + shot + revision, so retries never double-charge."""

from __future__ import annotations

from frameteller.application.ports import Job

GENERATE_PANEL = "generate_panel"
PRE_SEGMENT_PANEL = "pre_segment_panel"
EXPORT_ANIMATIC = "export_animatic"


def panel_key(kind: str, project_id: str, shot_id: str, revision: int) -> str:
    return f"{kind}:{project_id}:{shot_id}:r{revision}"


def pre_segment_job(project_id: str, shot_id: str, revision: int) -> Job:
    return Job(
        kind=PRE_SEGMENT_PANEL,
        idempotency_key=panel_key(PRE_SEGMENT_PANEL, project_id, shot_id, revision),
        payload={"project_id": project_id, "shot_id": shot_id, "revision": str(revision)},
    )
