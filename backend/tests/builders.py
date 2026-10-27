"""Test data: the original "Mira and the lantern cat" story from the spikes."""

from __future__ import annotations

from frameteller.domain import (
    Box,
    Character,
    Framing,
    MaskBitmap,
    MediaRef,
    Project,
    Shot,
    TranscriptTurn,
)

MIRA = Character("mira", "Mira", "8-year-old girl, yellow hooded raincoat, red scarf, dark rain boots")
CAT = Character("cat", "Grey Cat", "small grey kitten with glowing amber eyes")


def turn(n: int, start: int = 0, length: int = 4000, text: str = "") -> TranscriptTurn:
    start = start or (n - 1) * length
    return TranscriptTurn(f"t{n}", text or f"turn {n}", start, start + length)


def shot(n: int, *characters: str, turn_ids: tuple[str, ...] | None = None, duration_ms: int = 4000) -> Shot:
    return Shot(
        id=f"s{n}",
        number=n,
        framing=Framing.MEDIUM,
        character_ids=tuple(characters),
        setting="a narrow alley at night, rain",
        action=f"action {n}",
        dialogue="",
        source_turn_ids=turn_ids or (f"t{n}",),
        duration_ms=duration_ms,
    )


def project(*, approved: bool = True, shots: int = 3) -> Project:
    """A project with Mira and the cat, `shots` turns and shots, and (optionally) an approved cast."""
    p = Project(id="p1", title="The Lantern Cat")
    p.upsert_character(MIRA)
    p.upsert_character(CAT)
    if approved:
        p.bible.set_reference("mira", MediaRef("refs/mira.webp"))
        p.bible.set_reference("cat", MediaRef("refs/cat.webp"))
        p.bible.approve()
    for n in range(1, shots + 1):
        p.add_turn(turn(n))
    p.append_shots([shot(n, "mira") if n != 2 else shot(n, "mira", "cat") for n in range(1, shots + 1)])
    return p


def bitmap(left: int, top: int, right: int, bottom: int, fill: int = 1) -> MaskBitmap:
    w, h = right - left, bottom - top
    return MaskBitmap(Box(left, top, right, bottom), bytes([fill]) * (w * h))
