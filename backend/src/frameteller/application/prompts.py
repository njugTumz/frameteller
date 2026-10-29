"""Prompt builders. Pure functions so they can be unit-tested without a model."""

from __future__ import annotations

from collections.abc import Sequence

from frameteller.domain import Character, PanelStyle, Shot

STYLES = {
    PanelStyle.PENCIL: "hand-drawn pencil storyboard sketch, clean graphite lines, light grey wash, one accent colour",
    PanelStyle.PAPER_CUTOUT: (
        "paper cutout animation: flat shapes cut from coloured craft paper, visible paper grain and torn edges, "
        "layered with soft drop shadows, simple backgrounds"
    ),
}
NOT_PHOTOREAL = "Never photorealistic, never a photograph or 3D render."
ONLY_AS_DESCRIBED = (
    "Show only what the description says: no clothing, accessories or props it does not mention. "
    "An animal wears nothing unless the description says so."
)


def reference_prompt(c: Character, style: PanelStyle = PanelStyle.PENCIL, correction: str = "") -> str:
    """A neutral two-view sheet in the project's style. Panels copy their references' look, so the sheet sets it."""
    return (
        f"Character reference sheet for an original character named {c.name}: {c.canonical_description}. "
        "Show the same character twice side by side: a front view and a three-quarter view, full body, "
        "neutral standing pose, identical in both views. "
        f"{ONLY_AS_DESCRIBED} Plain light grey background, no text, no scenery. "
        f"Style: {STYLES[style]}. {NOT_PHOTOREAL}"
        + (f" Correction from the continuity review: {correction.strip().rstrip('.')}." if correction.strip() else "")
    )


def panel_prompt(shot: Shot, cast: Sequence[Character], style: PanelStyle = PanelStyle.PENCIL) -> str:
    """`cast` is the shot's characters; those with sheets are attached as references in the same order."""
    who = "; ".join(f"{c.name}: {c.canonical_description}" for c in cast)
    lines = [
        f"Storyboard panel, {shot.framing.value.replace('_', ' ')} framing. Keep key action in the central 16:9 band.",
        f"Setting: {shot.setting}. Action: {shot.action}.",
    ]
    if who:
        lines.append(f"Characters: {who}.")
    if sheets := [c.name for c in cast if c.reference is not None]:
        lines.append(
            f"The attached reference sheets show, in order: {', '.join(sheets)}. Each character appears exactly as "
            "in their reference sheet: same species, proportions, colours, markings and drawing style, with no "
            "added clothing, accessories or change of style."
        )
    lines.append(f"Style: {STYLES[style]}. {NOT_PHOTOREAL} No text, captions or panel borders.")
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


def clean_plate_prompt(target: str) -> str:
    """Remove one object for a clean plate (ADR 0010): the rest must stay as it was, so the cut-out fits back."""
    target = target.strip()
    if not target:
        raise ValueError("a clean plate needs an object to remove")
    return (
        f"Remove the {target} from the picture. Keep everything else identical: composition, background, "
        "lighting, drawing style and every other object. Fill the space it leaves with what would be behind it."
    )


def _join(items: Sequence[str]) -> str:
    quoted = [f"the {i}" for i in items]
    return quoted[0] if len(quoted) == 1 else ", ".join(quoted[:-1]) + " and " + quoted[-1]
