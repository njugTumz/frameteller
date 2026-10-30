# ADR 0019: What reaches Muse Image's content filter

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** Isaac Tumuti
- **Builds on:** [ADR 0004](0004-cast-approval.md) (cast approval), [ADR 0018](0018-outfits.md) (outfit sheets)

## Context

On Oct 30, production's Errors tab showed 7 of 29 Muse Image calls refused with `model_content_filtered`. Six came
from one tester's Halloween story about her young daughter, and one from another story.

The logs and the stored projects show the same pattern every time:

- **Every refusal was the first try at a character's everyday reference sheet.** No outfit sheet, panel, edit or
  clean plate was refused.
- **The refused descriptions had no exact ages.** They read "human female with average build and expressive face",
  "adult human female with round face…" and "adult human man of average build…". Each prompt asked for a
  "full body, neutral standing pose". A person's body ("build", "full body") was the common factor.
- **The existing retry ("by look and role") drew all seven on the second try.** The tester still waited
  5–26 s each time, and pressed Try again on the same sheet four times.
- **The director had turned "my daughter" into "human female".** So the girl was neither described as a child
  nor drawn as one.

## Decision

- **Every Muse Image prompt is cleaned on its way out.** `SafeImages` wraps the image port in the composition
  root, so sheets, outfit sheets, panels, edits and clean plates all pass through it.
  - Exact ages become an age group ("6-year-old" → "young").
  - Family relationships become neutral roles ("my daughter" → "the child", "her dad" → "the man").
  - Body words go ("average build", "full body", "slender").
  - The user's words are stored and shown unchanged; only the prompt changes.
- **People are drawn "fully clothed, friendly standing pose".** A young character is "a storybook illustration of a
  cheerful young character" with their look. Animals keep "full body".
- **A refusal gets one plainer try.** The caller may give the plainer wording (`ImageRequest.fallback_prompt`):
  - sheets give the proven "friendly cartoon character for an all-ages family story" wording, by look only;
  - panels give each character by look only;
  - edits get a generic version with no age words, and a child becomes "a character".
- **After two refusals, the sheet offers a concrete description.** The project keeps a `SheetRefusal` with the
  refused text and a suggestion. The cast tray shows the suggestion with a **Use this description** button.
  - Try again with the same description answers `409 edit_first`.
  - Any change to the description, and any drawn sheet, ends the block.
- **The director describes an age group, never an exact age, a family relationship or a body shape.** A child the
  narrator calls "my daughter" is "a young girl".

## Consequences

- No extra cost: refused prompts are not billed, and the one charge covers both tries.
- A body word the user meant ("a tall, broad baker") is not sent to the model. Their clothes, face and hair carry
  the look.
- Panels and edits refused twice still show the general message. In production none have been refused so far.
