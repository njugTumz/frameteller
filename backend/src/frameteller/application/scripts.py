"""Accept a pasted or uploaded script for the teleprompter or "Read it to me" (ADR 0015), within the demo limits."""

from __future__ import annotations

from frameteller.application.errors import ScriptError
from frameteller.application.limits import DemoLimits
from frameteller.domain import InvalidValueError, Script, ScriptFormat, parse_script


def accept_script(text: str, fmt: ScriptFormat, limits: DemoLimits | None) -> Script:
    """Parse the script and check it fits. Raises ScriptError with a message that says what to change."""
    if limits and len(text) > limits.script_characters:
        raise ScriptError(
            f"Scripts can be up to {limits.script_characters:,} characters in the public demo, and this one has "
            f"{len(text):,}. Shorten it or split it into another story."
        )
    try:
        script = parse_script(text, fmt)
    except InvalidValueError as e:
        raise ScriptError("There's nothing to tell in that script yet. Paste a paragraph or two.") from e
    if limits and len(script.episodes) > limits.episodes_per_script:
        raise ScriptError(
            f"This script has {len(script.episodes)} episodes; the public demo tells up to "
            f"{limits.episodes_per_script}. Remove the later ones and try again."
        )
    for episode in script.episodes:
        if limits and len(episode.beats) > limits.shots_per_episode:
            raise ScriptError(
                f"Episode {episode.number} has {len(episode.beats)} paragraphs; the public demo draws up to "
                f"{limits.shots_per_episode} shots per episode. Join some paragraphs or start a new episode."
            )
    return script
