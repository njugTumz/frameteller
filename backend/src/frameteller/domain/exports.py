"""What a project has exported, so the studio and share page can show it again."""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.domain.media import MediaRef


@dataclass(frozen=True, slots=True)
class AnimaticExport:
    video: MediaRef
    duration_ms: int
    subtitles: bool
    voiced: bool  # False when no narration was kept: the animatic is silent
