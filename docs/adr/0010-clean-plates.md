# ADR 0010: Saved geometry on a clean plate

- **Status:** Accepted
- **Date:** 2026-10-28
- **Deciders:** Isaac Tumuti
- **Amends:** [ADR 0005](0005-edits-geometry-vs-appearance.md)

## Context

ADR 0005 keeps geometry (move, resize, delete) on our canvas, pasting SAM cut-outs, with no image-model call. That left a ghost: when an object moves, the original pixels are still drawn underneath it. The editor could only preview a move; it could not be saved into the storyboard, animatic or share page.

Muse Image has no masked edits and no inpainting, but a whole-panel prompt edit keeps the layout (at most 0.6% structural change outside the object, [Day 2 findings](../spikes/2026-10-28-findings.md)). So it can remove one object and leave the rest in place.

## Decision

- **Layers.** A move, resize or delete is saved as a layer on the panel (`POST /projects/{id}/shots/{n}/panel/layers`, `MovePanelObject`). A layer holds the object id, `dx`, `dy` and `scale` from the cut-out's top-left, and `deleted`. There is at most one layer per object, and moving an object home removes its layer.
- **Clean plate.** The first time an object gets a layer, a `compose_panel` job asks Muse Image to remove it: "Remove the *visual noun phrase* from the picture. Keep everything else identical…". The edit is chained from the render's `previous_response_id`. A character is named by its visual phrase ("8-year-old girl"), not its name. Plates are cached on the panel per base revision and keyed by the set of removed objects. Moving the same object again is free. A second object costs one more edit, chained from the cached plate.
- **Composite.** Pillow pastes each non-deleted cut-out on the plate at its layer's place and scale, server-side (`CompositorPort`, `PillowCompositor`). The result is stored as a WebP and becomes the panel's next *shown* revision. The base render keeps its own revision, masks and response id, so clicks and appearance edits still work on it.
- **New renders.** A redraw or appearance edit is a new base revision and drops plates and the composite. Layers of characters (stable `character:<id>` masks, ADR 0006) are kept and re-composited once the new render is pre-segmented. Layers of clicked objects cannot be found again and are dropped.
- **Idempotency.** The job key is the project, shot, base revision, and a digest of the layers and the shown revision. Double-clicks compose once, and moving back to an earlier arrangement composes again.

## Consequences

- Saved moves cost $0.01 per object per render, once. Compositing is free and takes well under a second.
- The editor shows "Preparing the background…" while the job runs (~20 s, the image edit).
- The removal redraws fine texture across the whole panel (ADR 0005). Small differences around other objects can show, but nothing is left behind.
- The storyboard, animatic, PDF and share page all show `image_url`: the composite once it exists, otherwise the render.
