"""A written script: episodes of beats, one beat per paragraph (ADR 0015).

Plain text, Markdown and Fountain (a plain-text screenplay format) are parsed here without a library:
- A blank line ends a paragraph, and each paragraph becomes one beat.
- A line "Episode 2" (also "EPISODE 2", "Ep. 2", "# Episode 2: The Storm") starts a new episode.
- Framing cues ("Wide shot.", "Close-up on the lamp.") stay in the beat's direction for the director, but are
  not read aloud. A paragraph of cues alone directs the next beat.
- Fountain scene headings ("INT. LIGHTHOUSE - NIGHT") direct the next beat, character cues turn their dialogue
  into a beat ("Ada says: …"), and transitions, notes, sections, synopses and the title page are dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from frameteller.domain.errors import InvalidValueError


class ScriptFormat(StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    FOUNTAIN = "fountain"


@dataclass(frozen=True, slots=True)
class ScriptBeat:
    narration: str  # what is read aloud (by the user or a voice), cues removed
    direction: str  # what the director reads: the paragraph with its cues and scene heading


@dataclass(frozen=True, slots=True)
class Episode:
    number: int
    beats: tuple[ScriptBeat, ...]


@dataclass(frozen=True, slots=True)
class Script:
    episodes: tuple[Episode, ...]

    @property
    def beats(self) -> tuple[tuple[int, ScriptBeat], ...]:
        """Every beat in reading order, with its episode number."""
        return tuple((e.number, b) for e in self.episodes for b in e.beats)


EPISODE = re.compile(r"^\s*#*\s*(?:episode|ep\.?)\s*(\d{1,3})\b[\s:.\-\u2013\u2014]*(.*)$", re.IGNORECASE)
_FRAMING = (
    r"(?:extreme\s+)?(?:wide|long|medium|close|establishing|aerial|tracking|two|insert|master|full|cowboy|"
    r"over[- ]the[- ]shoulder|low[- ]angle|high[- ]angle|bird'?s[- ]eye|pov|point[- ]of[- ]view)"
)
FRAMING_CUE = re.compile(
    rf"^(?:(?:{_FRAMING})(?:[- ]?(?:shot|up|angle|view))?|close[- ]?up|close on|angle on|cut to|pan (?:to|across)|"
    r"(?:slow )?(?:push[- ]in|pull[- ]back|dolly(?: in| out)?|crane (?:up|down))|"
    r"zoom (?:in|out)|fade (?:in|out)|smash cut|match cut)\b",
    re.IGNORECASE,
)
SENTENCE = re.compile(r"[^.!?…]+(?:[.!?…]+[\"')\]]*|$)")
SCENE_HEADING = re.compile(r"^(?:INT|EXT|EST|INT\.?/EXT|I/E)[.\s]", re.IGNORECASE)
TRANSITION = re.compile(r"^[A-Z0-9 ]+TO:$")
CHARACTER = re.compile(r"^@?[A-Z][A-Z0-9 .'\-]*(?:\s*\([^)]*\))?\s*\^?$")
TITLE_KEY = re.compile(r"^(?:title|credit|author|authors|source|draft date|date|contact|notes|copyright)\s*:", re.I)


def is_episode_heading(line: str) -> bool:
    return bool(EPISODE.match(line)) and len(line.strip()) <= 80


MAX_CUE_WORDS = 5  # "Close-up on the lamp." is a cue; "Close-up on her hands as she frees the kite." is told


def split_cues(paragraph: str) -> tuple[str, str]:
    """(narration, cues): short sentences that start with a framing term are cues, the rest is read aloud."""
    spoken: list[str] = []
    cues: list[str] = []
    for sentence in (m.group(0).strip() for m in SENTENCE.finditer(paragraph)):
        if sentence:
            cue = FRAMING_CUE.match(sentence) and len(sentence.split()) <= MAX_CUE_WORDS
            (cues if cue else spoken).append(sentence)
    return " ".join(spoken), " ".join(cues)


def _clean_markdown(line: str) -> str:
    line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)  # list markers
    line = re.sub(r"^\s*>\s?", "", line)  # quotes
    return re.sub(r"(\*\*|__|\*|_|`)(.+?)\1", r"\2", line)


def _strip_fountain_noise(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)  # boneyard
    return re.sub(r"\[\[.*?\]\]", "", text, flags=re.DOTALL)  # notes


def _blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = [[]]
    for line in lines:
        if line.strip():
            blocks[-1].append(line.rstrip())
        elif blocks[-1]:
            blocks.append([])
    return [b for b in blocks if b]


class _Builder:
    def __init__(self) -> None:
        self.episodes: list[list[ScriptBeat]] = [[]]
        self.pending_direction: list[str] = []  # a scene heading or a cue-only paragraph, for the next beat

    def episode(self) -> None:
        if self.episodes[-1] or len(self.episodes) > 1:
            self.episodes.append([])
        self.pending_direction = []

    def direct_next(self, text: str) -> None:
        self.pending_direction.append(text)

    def paragraph(self, text: str, *, narration: str | None = None) -> None:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return
        spoken, cues = split_cues(text)
        if narration is not None:
            spoken = narration
        if not spoken:  # cues alone, like "Wide shot.": they direct the next beat
            self.direct_next(cues)
            return
        direction = " ".join([*self.pending_direction, text])
        self.pending_direction = []
        self.episodes[-1].append(ScriptBeat(spoken, direction))

    def build(self) -> Script:
        if self.pending_direction and self.episodes[-1]:  # cues after the last beat still direct it
            last = self.episodes[-1][-1]
            extra = " ".join(self.pending_direction)
            self.episodes[-1][-1] = ScriptBeat(last.narration, f"{last.direction} {extra}")
        episodes = [e for e in self.episodes if e]
        return Script(tuple(Episode(n, tuple(beats)) for n, beats in enumerate(episodes, start=1)))


def parse_script(text: str, fmt: ScriptFormat = ScriptFormat.TEXT) -> Script:
    """Parse a script. Raises InvalidValueError if nothing in it can be told."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    if fmt is ScriptFormat.FOUNTAIN:
        script = _parse_fountain(text)
    else:
        b = _Builder()
        for block in _blocks(text.split("\n")):
            lines = [_clean_markdown(x) if fmt is ScriptFormat.MARKDOWN else x for x in block]
            for line in lines:
                if is_episode_heading(line):
                    b.episode()
            rest = [x for x in lines if not is_episode_heading(x)]
            if fmt is ScriptFormat.MARKDOWN:
                rest = [x for x in rest if not x.lstrip().startswith("#")]  # titles and section headings
            b.paragraph(" ".join(rest))
        script = b.build()
    if not script.episodes:
        raise InvalidValueError("the script has no paragraphs to tell")
    return script


def _parse_fountain(text: str) -> Script:
    blocks = _blocks(_strip_fountain_noise(text).split("\n"))
    if blocks and all(TITLE_KEY.match(x) or x.startswith((" ", "\t")) for x in blocks[0]):
        blocks = blocks[1:]  # the title page
    b = _Builder()
    for block in blocks:
        first = block[0].strip()
        if is_episode_heading(first.lstrip("#").strip()) and len(block) == 1:
            b.episode()
        elif first.startswith(("#", "=")) and len(block) == 1:
            continue  # a section or a synopsis
        elif (SCENE_HEADING.match(first) or (first.startswith(".") and not first.startswith(".."))) and len(block) == 1:
            b.direct_next("Scene: " + first.lstrip(".").strip().rstrip(".") + ".")
        elif (TRANSITION.match(first) or first.startswith(">")) and len(block) == 1 and not first.endswith("<"):
            continue  # CUT TO:
        elif len(block) > 1 and CHARACTER.match(first) and not SCENE_HEADING.match(first):
            name = re.sub(r"\s*\(.*\)\s*|\^|@", "", first).strip().title()
            lines = [x.strip() for x in block[1:] if not x.strip().startswith("(")]
            dialogue = " ".join(lines)
            b.paragraph(f'{name} says: "{dialogue}"', narration=f"{name} says: {dialogue}")
        else:
            lines = [x.strip().lstrip("!").removeprefix(">").removesuffix("<").strip() for x in block]
            b.paragraph(" ".join(lines))
    return b.build()
