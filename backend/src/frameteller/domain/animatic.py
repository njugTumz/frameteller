"""Animatic timeline: one clip per shot, timed from the narration turns."""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.domain.errors import PanelNotReadyError
from frameteller.domain.media import MediaRef
from frameteller.domain.panels import CanvasTransform
from frameteller.domain.project import Project


@dataclass(frozen=True, slots=True)
class AnimaticClip:
    shot_id: str
    image: MediaRef
    start_ms: int
    duration_ms: int
    transforms: tuple[CanvasTransform, ...] = ()


@dataclass(frozen=True, slots=True)
class Animatic:
    project_id: str
    clips: tuple[AnimaticClip, ...]
    narration: MediaRef | None = None

    @property
    def duration_ms(self) -> int:
        return sum(c.duration_ms for c in self.clips)

    @classmethod
    def from_project(cls, project: Project, narration: MediaRef | None = None) -> Animatic:
        """Clips in shot order, back to back. Every shot needs a ready panel."""
        clips, t = [], 0
        for shot in project.shots:
            panel = project.panels.get(shot.id)
            if panel is None:
                raise PanelNotReadyError(f"shot {shot.number} has no panel")
            image, _ = panel.require_ready()
            clips.append(AnimaticClip(shot.id, image, t, shot.duration_ms, tuple(panel.transforms)))
            t += shot.duration_ms
        if not clips:
            raise PanelNotReadyError("nothing to export: the project has no shots")
        return cls(project.id, tuple(clips), narration)
