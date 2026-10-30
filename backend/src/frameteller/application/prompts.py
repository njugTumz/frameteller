"""Prompt builders. Pure functions so they can be unit-tested without a model."""

from __future__ import annotations

from collections.abc import Sequence

from frameteller.application.image_safety import appearance_only, is_person, is_young, sanitize, suggest_description
from frameteller.domain import Character, Look, PanelStyle, Shot

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


def _who(description: str, *, safer: bool) -> str:
    """How a character is named in a sheet prompt (ADR 0019). A young character is a cheerful storybook character;
    `safer`, the one retry after a refusal, is by look only, with no age, gender or family words."""
    look = appearance_only(description)
    if safer:
        lead = "a friendly cartoon character for an all-ages family story"
        return f"{lead}, with {look}" if look else lead
    if is_young(description):
        lead = "a storybook illustration of a cheerful young character"
        return f"{lead}, with {look}" if look else lead
    return sanitize(description)


def _pose(description: str, *, safer: bool) -> str:
    """People are drawn fully clothed in a friendly pose: Muse Image refused "full body" next to a person (Oct 29
    with a child, Oct 30 with adults). An animal is not dressed up."""
    if safer or is_young(description) or is_person(description):
        return "fully clothed, friendly standing pose"
    return "full body, neutral standing pose"


def reference_prompt(
    c: Character, style: PanelStyle = PanelStyle.PENCIL, correction: str = "", *, safer: bool = False
) -> str:
    """A neutral two-view sheet in the project's style. Panels copy their references' look, so the sheet sets it.

    `safer` is the one retry after a refusal (ADR 0019); `SafeImages` cleans both on the way out."""
    who = _who(c.canonical_description, safer=safer)
    pose = _pose(c.canonical_description, safer=safer)
    return (
        f"Character reference sheet for an original character named {c.name}: {who}. "
        f"Show the same character twice side by side: a front view and a three-quarter view, {pose}, "
        "identical in both views. "
        f"{ONLY_AS_DESCRIBED} Plain light grey background, no text, no scenery. "
        f"Style: {STYLES[style]}. {NOT_PHOTOREAL}"
        + (f" Correction from the continuity review: {correction.strip().rstrip('.')}." if correction.strip() else "")
    )


def look_reference_prompt(
    c: Character, look: Look, style: PanelStyle = PanelStyle.PENCIL, correction: str = "", *, safer: bool = False
) -> str:
    """A sheet for another outfit of the same character (ADR 0018), drawn from their everyday sheet when it is
    attached: the same person, only the clothes change."""
    who = _who(c.canonical_description, safer=safer)
    pose = _pose(c.canonical_description, safer=safer)
    clothes = look.clothes.strip().rstrip(".")
    return (
        f"Character reference sheet for an original character named {c.name}, in a new outfit: the "
        f"{look.label.strip().lower()}. The same character as in the attached reference sheet, with the same face, "
        "hair, colouring, proportions and drawing style; only the clothes change. "
        f"Who they are: {who}. Ignore any clothes in that description: now they wear {sanitize(clothes)}. "
        f"Show the same character twice side by side: a front view and a three-quarter view, {pose}, "
        "identical in both views. Plain light grey background, no text, no scenery. "
        f"Style: {STYLES[style]}. {NOT_PHOTOREAL}"
        + (f" Correction from the continuity review: {correction.strip().rstrip('.')}." if correction.strip() else "")
    )


def panel_prompt(
    shot: Shot, cast: Sequence[Character], style: PanelStyle = PanelStyle.PENCIL, *, safer: bool = False
) -> str:
    """`cast` is the shot's characters; those with sheets are attached as references in the same order.
    `safer`, the retry after a refusal, describes each character by look only (ADR 0019)."""
    describe = suggest_description if safer else sanitize
    who = "; ".join(f"{c.name}: {describe(c.canonical_description)}" for c in cast)
    lines = [
        f"Storyboard panel, {shot.framing.value.replace('_', ' ')} framing. Keep key action in the central 16:9 band.",
        f"Setting: {sanitize(shot.setting)}. Action: {sanitize(shot.action)}.",
    ]
    if who:
        lines.append(f"Characters: {who}.")
    if sheets := [c.name for c in cast if c.reference is not None]:
        lines.append(
            f"The attached reference sheets show, in order: {', '.join(sheets)}. Each character appears exactly as "
            "in their reference sheet: same species, proportions, colours, markings, clothes and drawing style, "
            "with no added clothing, accessories or change of style."
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
