# ADR 0014: Edit from our stored images, never from a response chain

- **Status:** Accepted
- **Date:** 2026-10-29
- **Deciders:** Isaac Tumuti
- **Amends:** [ADR 0003](0003-panel-aspect-ratio.md) (panels "stay editable multi-turn"), [ADR 0005](0005-edits-geometry-vs-appearance.md) and [ADR 0010](0010-clean-plates.md) (edits and clean plates "chained from `previous_response_id`")

## Context

Every Muse Image edit used to chain on the panel's Responses id (`previous_response_id`): the model kept the image, we sent only the change. A user can make that edit at any time after the panel was drawn: an appearance edit by voice, a supervisor fix, or the clean plate behind a move.

On production (2026-10-29, v0.10.0) a move failed: the clean plate's edit got HTTP 400 "referenced response not found or expired" for a panel drawn about two minutes earlier. Meta's docs do not say how long a response stays usable. Spike 4 (`spikes/s4_edit_source.py`, one lighthouse panel) measured it:

| Chain from | Age | Result |
|---|---|---|
| A panel drawn by the app (references as input images) | 49 min | ok |
| A response created by an edit with input images | at once, 3 min, 6 min | 400 "referenced response not found or expired" |
| Production: a draft panel | about 2 min | 400 "referenced response not found or expired" |

So retention is not a clock we can design around. Some responses chain for an hour, others never.

The same spike compared editing from our stored copy: the panel as the first `input_image`, the character's reference sheet after it, and the change ("Edit the first image. … Keep the composition, framing, poses, lighting, line work and style of the first image exactly."). Structural change outside the character was measured after a 6 px blur, the method of spike 3:

| Edit | Structural change outside the character | Inside | Latency |
|---|---|---|---|
| Stored image, sweater green → red | **0.21%** | 37.7% | 16.5 s |
| Stored image, sweater red → blue | **0.17%** | 37.9% | 17.4 s |
| Chained, red coat (spike 3, for comparison) | 0.6% | 35.2% | 25 s |

Both stored-image edits applied the change and kept the layout at least as well as a chain. Fine texture is redrawn either way (about 23% of raw pixels differ), as before.

## Decision

- **Every edit sends our stored image.** `ImageGenerationPort.edit(EditRequest(image, prompt, quality, references), store_as)`:
  - The image goes first, then the reference sheets of the shot's characters, all as `input_image` parts in one user message.
  - `previous_response_id` is never sent. There is no retry-with-chain path, because there is no chain.
- **Where it applies:**
  - Appearance edits by voice or click (`EditPanelAppearance`), and so supervisor fixes and "Apply suggested fix", which go through it.
  - Clean plates (`ComposePanel`): the first removal edits the stored render, and each further removal edits the cached plate image.
- **Response ids are still recorded** on panels and plates, for tracing a render back to Meta's logs. Nothing reads them to make a request.
- **Cost is unchanged.** It is a flat USD 0.01 per generated image; the extra input images are not billed.

## Consequences

- A move, an edit or a fix works the same an hour or a day after the panel was drawn. The user never sees "expired".
- The request carries 1–4 images (about 0.3–1.2 MB of base64) instead of an id. Latency was no worse in the spike.
- The adapter owns the wording that tells the model which image to edit. The application still builds the change itself (`edit_prompt`, `clean_plate_prompt`), so ADR 0005's part-naming is unchanged.
- CLAUDE.md section 5 now records the observed retention, and its open question "retention period for `previous_response_id`" is closed: it is unreliable, so we do not depend on it.
