"""What a project has exported, so the studio and share page can show it again."""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.domain.media import MediaRef


@dataclass(frozen=True, slots=True)
class AnimaticExport:
    video: MediaRef
    duration_ms: int
    subtitles: bool  # captions burned into the picture
    voiced: bool  # False when no narration was kept: the animatic is silent
    captions: MediaRef | None = None  # the same captions as an .srt file (also a soft track in the MP4)
    caption_language: str = ""  # the captions' locale when translated ("fr-FR"); "" as spoken
