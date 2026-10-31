"""Animatic timeline: one clip per shot, timed and voiced from the narration turns (ADR 0011)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from frameteller.domain.errors import PanelNotReadyError, UnknownTurnError
from frameteller.domain.media import MediaRef
from frameteller.domain.narration import session_of
from frameteller.domain.project import Project
from frameteller.domain.shots import Framing, Shot, voice_offsets
from frameteller.domain.text import join, tokens

TITLE_MS = 1000  # the title card before the first shot
END_MS = 1500  # the "Made with Frameteller" card after the last


class Motion(StrEnum):
    """A gentle camera move on the still panel, chosen by framing."""

    PUSH_IN = "push_in"  # wide: slow push towards the centre
    DRIFT = "drift"  # close-up: slight sideways drift
    STATIC = "static"


def motion_for(framing: Framing) -> Motion:
    if framing is Framing.WIDE:
        return Motion.PUSH_IN
    if framing is Framing.CLOSE_UP:
        return Motion.DRIFT
    return Motion.STATIC


@dataclass(frozen=True, slots=True)
class AudioCut:
    """A stretch of one kept narration recording, in milliseconds from the start of that recording."""

    recording: MediaRef
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True, slots=True)
class AnimaticClip:
    shot_id: str
    number: int
    image: MediaRef  # the panel as shown: its composite when objects were moved
    start_ms: int
    duration_ms: int
    motion: Motion = Motion.STATIC
    caption: str = ""  # the words spoken over this shot, for optional subtitles
    audio: tuple[AudioCut, ...] = ()  # the narrator's voice for this shot; padded or cut to duration_ms


@dataclass(frozen=True, slots=True)
class Animatic:
    project_id: str
    title: str
    clips: tuple[AnimaticClip, ...]

    @property
    def duration_ms(self) -> int:
        return sum(c.duration_ms for c in self.clips)

    @property
    def has_voice(self) -> bool:
        return any(c.audio for c in self.clips)

    @classmethod
    def from_project(cls, project: Project) -> Animatic:
        """Clips in shot order, back to back. Every shot needs a ready panel.

        A shot's voice is the part of its turn's recording it took its time from: the shots of one turn share
        the turn in order (ADR 0008), so the first gets the start of the turn, the next what follows. Reordered
        shots take their voice with them. Shots from a session whose audio was not kept are silent.
        """
        if not project.shots:
            raise PanelNotReadyError("nothing to export: the project has no shots")
        by_turn: dict[str, list[Shot]] = defaultdict(list)
        for shot in sorted(project.shots, key=lambda s: s.number):  # spoken order within a turn
            if len(shot.source_turn_ids) == 1:
                by_turn[shot.source_turn_ids[0]].append(shot)
        voiced = {s.id: v for shots in by_turn.values() for s, v in zip(shots, _share(project, shots), strict=True)}

        clips, t = [], 0
        for shot in project.shots:
            panel = project.panels.get(shot.id)
            if panel is None:
                raise PanelNotReadyError(f"shot {shot.number} has no panel")
            panel.require_ready()
            image = panel.shown_image
            assert image is not None  # a ready panel has an image
            caption, audio = voiced.get(shot.id) or _whole_turns(project, shot)
            clips.append(
                AnimaticClip(shot.id, shot.number, image, t, shot.duration_ms, motion_for(shot.framing), caption, audio)
            )
            t += shot.duration_ms
        return cls(project.id, project.title, tuple(clips))


def _share(project: Project, shots: list[Shot]) -> list[tuple[str, tuple[AudioCut, ...]]]:
    """Split one turn's words and recording between its shots, in order, by their durations."""
    try:
        turn = project.turn(shots[0].source_turn_ids[0])
    except UnknownTurnError:
        return [("", ())] * len(shots)
    narration = project.narrations.get(session_of(turn.id))
    words = tokens(turn.text)  # characters in Japanese and Chinese
    starts = voice_offsets(shots)
    gaps = any(s.voice_from_ms is not None for s in shots)  # a sibling was deleted: words follow the time
    total = (turn.duration_ms if gaps else sum(s.duration_ms for s in shots)) or 1
    out, taken = [], 0
    for i, (shot, offset) in enumerate(zip(shots, starts, strict=True)):
        last = i == len(shots) - 1 and not gaps
        if gaps:
            taken = min(len(words), round(len(words) * offset / total))
        upto = len(words) if last else min(len(words), round(len(words) * (offset + shot.duration_ms) / total))
        caption = join(words[taken:upto])
        audio: tuple[AudioCut, ...] = ()
        if narration is not None:
            start = min(turn.start_ms + offset, narration.duration_ms)
            end = min(start + shot.duration_ms, narration.duration_ms)
            audio = (AudioCut(narration.recording, start, end),) if end > start else ()
        out.append((caption, audio))
        taken = upto
    return out


def _whole_turns(project: Project, shot: Shot) -> tuple[str, tuple[AudioCut, ...]]:
    """A shot made from several turns (a correction can merge them) gets all of them, back to back."""
    captions, cuts = [], []
    for turn_id in shot.source_turn_ids:
        try:
            turn = project.turn(turn_id)
        except UnknownTurnError:
            continue
        captions.append(turn.text)
        narration = project.narrations.get(session_of(turn.id))
        if narration is not None and turn.start_ms < narration.duration_ms:
            cuts.append(AudioCut(narration.recording, turn.start_ms, min(turn.end_ms, narration.duration_ms)))
    return " ".join(captions), tuple(c for c in cuts if c.duration_ms > 0)
