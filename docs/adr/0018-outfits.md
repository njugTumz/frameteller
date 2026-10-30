# ADR 0018: Outfits that carry forward

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Isaac Tumuti
- **Builds on:** [ADR 0004](0004-cast-approval.md) (one sheet per character, cast approval), [ADR 0012](0012-continuity-supervisor.md) (the supervisor)

## Context

A tester told a Halloween story: in paragraph 2 her daughter puts on a farmer costume (overalls, white shirt, red
bandana, cowgirl boots). Only shot 2 showed it. Every later panel went back to the pyjamas on the girl's only
reference sheet, even shot 3, whose action said "in her farmer costume". The supervisor checked those panels
against the same sheet and passed them.

A sheet is the strongest signal Muse Image gets about a character, stronger than the prompt. So one sheet per
character cannot show a costume change. The fix has to change the sheet, not only the words.

## Decision

- **A look is an outfit with its own sheet.** A character keeps one canonical description and one everyday sheet.
  Each outfit is a `Look`: id (`farmer_costume`), label ("Farmer costume"), the clothes only, and its own sheet.
- **Outfit changes start at a shot and carry forward.** The project keeps `OutfitChange(character, look,
  from_shot)` entries. A shot's look is the latest change at or before it; `everyday` changes back.
  - Carrying forward is done in code, not by asking the model shot by shot.
  - Changes follow their shot. If the shot is deleted, the change moves to the next shot.
  - A re-directed turn (a correction) records its changes again.
- **The director records changes.** Muse Spark returns `outfit_changes`, each with `from_shot`: one of the turn's
  new shots, or one of the last 3 shots for a reveal ("she had already changed").
  - Validation checks the character and the shot, and on failure asks once more with the error.
  - The bible message lists each character's looks. The shots so far say who wears what.
- **A look's sheet is drawn from the everyday sheet.** The everyday sheet goes in as the reference image, and the
  prompt says: same face, hair, build and style; only the clothes change.
  - Sheets are drawn everyday first, then looks.
  - A new everyday description drops the looks' sheets, and the same job draws them again.
- **A new look returns the cast to draft,** like a new character: the user approves the sheet before panels use it.
  - The cast tray shows each look with Try again and Edit description.
  - Editing a look's clothes redraws only that sheet and marks its panels outdated.
- **Every per-shot use goes through `Project.cast_in(shot)`.** Each character comes back in the look they wear,
  with that look's sheet and the clothes added to their description. This covers panels, the supervisor, edits
  and edit routing.
- **The rubric checks the outfit.** `panel-continuity` v2 judges clothes against the outfit worn in that shot
  (CONT-09).

## Consequences

- A costume costs one more sheet ($0.01), and one more approval click mid-story.
- Panels already drawn in the old clothes are marked outdated, not redrawn on their own.
- Look sheets are not reviewed by the supervisor's sheet check yet. The panels drawn from them are.
