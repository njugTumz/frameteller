"""Prompt builders. Pure functions so they can be unit-tested without a model."""

from __future__ import annotations

from collections.abc import Sequence

from frameteller.domain import Character, PanelStyle, Shot

STYLES = {
    PanelStyle.PENCIL: "clean pencil storyboard sketch, light grey wash, one accent colour",
    PanelStyle.PAPER_CUTOUT: (
        "paper cutout animation: flat shapes cut from coloured craft paper, visible paper grain and torn edges, "
        "layered with soft drop shadows, simple backgrounds"
    ),
}


def reference_prompt(c: Character, style: PanelStyle = PanelStyle.PENCIL) -> str:
    prompt = (
        f"Character reference sheet for an original character named {c.name}: {c.canonical_description}. "
        "Show the same character twice side by side: a front view and a three-quarter view, full body, "
        "neutral standing pose, identical outfit and colours in both views. Plain light grey background, "
        "no text, no props, no scenery."
    )
    # Pencil sheets keep the wording measured in the Day 2 spikes; other styles say how to draw the sheet,
    # because panels copy their references' look.
    return prompt if style is PanelStyle.PENCIL else f"{prompt} Style: {STYLES[style]}."


def panel_prompt(shot: Shot, cast: Sequence[Character], style: PanelStyle = PanelStyle.PENCIL) -> str:
    who = "; ".join(f"{c.name}: {c.canonical_description}" for c in cast)
    lines = [
        f"Storyboard panel, {shot.framing.value.replace('_', ' ')} framing. Keep key action in the central 16:9 band.",
        f"Setting: {shot.setting}. Action: {shot.action}.",
    ]
    if who:
        lines.append(f"Characters: {who}. Draw each exactly as in the attached reference sheets.")
    lines.append(f"Style: {STYLES[style]}. No text, captions or panel borders.")
    return " ".join(lines)


def concept_phrase(c: Character, max_words: int = 8) -> str:
    """A short visual noun phrase for SAM, which finds "girl in yellow raincoat" but not "Mira" (ADR 0006).

    The first clause of the canonical description, which the director writes as who-or-what first.
    """
    first = c.canonical_description.replace(";", ",").split(",")[0].split(".")[0].strip()
    words = first.split()[:max_words]
    return " ".join(words) if words else c.name


def edit_prompt(change: str, target: str, parts: Sequence[str]) -> str:
    """Appearance edit that names every affected part, so none is left behind (ADR 0005)."""
    change, target = change.strip().rstrip("."), target.strip()
    if not change or not target:
        raise ValueError("an edit needs a change and a target")
    named = [p.strip() for p in parts if p.strip()]
    scope = f"the {target}" + (f", including {_join(named)}" if named else "")
    return (
        f"Edit {scope}: {change}. Apply the change to every part listed. "
        "Keep the composition, pose, size, position and everything else in the panel identical."
    )


def _join(items: Sequence[str]) -> str:
    quoted = [f"the {i}" for i in items]
    return quoted[0] if len(quoted) == 1 else ", ".join(quoted[:-1]) + " and " + quoted[-1]
