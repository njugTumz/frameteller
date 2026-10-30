"""Test data: the original "Mira and the lantern cat" story from the spikes."""

from __future__ import annotations

from dataclasses import replace

from frameteller.domain import (
    Box,
    Character,
    Framing,
    Look,
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


# "The lighthouse fox": a user's test story (spikes/fixtures/lighthouse.txt). Paragraph 3 is vague on purpose;
# paragraph 4 reveals it was Pip. The director once invented a butterfly called Ember for it.
LIGHTHOUSE = (
    "A tiny lighthouse on a rock in the middle of a stormy sea. Waves crash all around it.",
    "Inside, an old woman named Ada with silver hair and a thick green sweater is polishing the big lamp.",
    "Close-up on the window. Something small and orange is flapping against the glass in the wind.",
    "Ada opens the window, and a soaked little fox named Pip tumbles inside and shakes off the rain.",
    "Medium shot. Ada wraps Pip in a blanket by the fire. They both watch the storm.",
    "Wide shot. At dawn the sea is calm, and Ada and Pip sit together on the rock watching the sunrise.",
)
ADA = Character("ada", "Ada", "elderly woman with long silver hair, wrinkled face, thick green knit sweater")
PIP = Character("pip", "Pip", "tiny young fox kit with damp reddish-brown fur, white chest and muzzle, fluffy tail")
EMBER = Character("ember", "Ember", "tiny orange butterfly with black-edged wings")


def lighthouse_turn(n: int) -> TranscriptTurn:
    return TranscriptTurn(f"t{n}", LIGHTHOUSE[n - 1], (n - 1) * 8000, n * 8000)


# "The farmer costume": a tester's bug report (Oct 30), retold with an invented girl, Wren
# (spikes/fixtures/costume.txt). Paragraph 2 puts the costume on; every later panel must keep it.
COSTUME = (
    "Saturday morning in a cosy kitchen. Wren, a little girl with curly brown hair and freckles, sits at the table "
    "in purple pyjamas and tells her dad she wants to be a farmer for Halloween.",
    "In her bedroom, Wren puts on her farmer costume: blue denim overalls over a white shirt, a red bandana around "
    "her neck and brown cowgirl boots. She looks in the mirror and grins.",
    "Wren runs down the stairs and spins around to show her dad, who claps.",
    "That evening, Wren walks down the street holding a pumpkin bucket, past houses with glowing jack-o'-lanterns.",
    "She knocks on a neighbour's door and holds up her bucket with a big smile.",
    "Back home, Wren tips her sweets out on the kitchen table and counts them one by one.",
)
WREN = Character("wren", "Wren", "human little girl, light skin, freckles, curly brown hair, purple pyjamas")
DAD = Character("dad", "Dad", "human adult man, short brown hair, light blue t-shirt, grey trousers")
FARMER = Look(
    "farmer_costume",
    "Farmer costume",
    "blue denim overalls over a white shirt, a red bandana around her neck, brown cowgirl boots",
)


def costume_turn(n: int) -> TranscriptTurn:
    return TranscriptTurn(f"t{n}", COSTUME[n - 1], (n - 1) * 8000, n * 8000)


def costume_project(*, looks: bool = True) -> Project:
    """The costume story directed into six shots, the cast drawn and approved; with `looks`, the costume recorded
    from shot 2 as the director does now."""
    p = Project(id="p1", title="The Farmer Costume")
    p.upsert_character(WREN)
    p.upsert_character(DAD)
    p.bible.set_reference("wren", MediaRef("refs/wren.webp"))
    p.bible.set_reference("dad", MediaRef("refs/dad.webp"))
    cast = {1: ("wren", "dad"), 3: ("wren", "dad")}
    for n in range(1, 7):
        p.add_turn(costume_turn(n))
    p.append_shots([replace(shot(n, *cast.get(n, ("wren",))), duration_ms=8000) for n in range(1, 7)])
    if looks:
        p.change_outfit("wren", FARMER, "s2")
        p.bible.set_look_reference("wren", "farmer_costume", MediaRef("refs/wren-farmer.webp"))
    p.bible.approve()
    return p
