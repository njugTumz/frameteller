# ADR 0005: Geometry on our canvas, appearance by prompt

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** Isaac Tumuti

## Context

Muse Image does not support masked edits. The [Day 2 spikes](../spikes/2026-10-28-findings.md) measured whole-panel edits chained with `previous_response_id`, using a SAM mask to compare before and after:

- "Make her raincoat red": the coat body turned red but **the hood stayed yellow**. Layout outside the subject changed by 0.6% (structural).
- "Make her larger": her box area grew by only **3%**.
- Every edit redraws fine texture (about 20% of pixels differ), so edits are not pixel-identical.

## Decision

- **Geometry** (move, resize, delete, swap) happens on our canvas using SAM cut-outs, with no image-model call.
- **Appearance** (colour, clothing, expression, props) uses chained Muse Image prompt edits naming the selected object.
- Edit prompts **name every affected part** of the object. The application builds the prompt from the object label and its parts (e.g. "raincoat, including the hood and sleeves"), so partial edits like the yellow hood do not happen.
- Canvas transforms are re-applied on top of the latest prompt-edited revision, because prompt edits redraw the texture underneath.

## Consequences

- Geometry edits are instant and free; appearance edits cost one image ($0.01) and ~20 s.
- Panels are layered: a base revision from the model plus an ordered list of canvas operations.
