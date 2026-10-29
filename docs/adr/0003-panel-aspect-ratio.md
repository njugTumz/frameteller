# ADR 0003: 3:2 panels via the Responses API

- **Status:** Accepted; amended by [ADR 0014](0014-edit-from-stored-images.md): edits send the stored image, never a `previous_response_id` chain
- **Date:** 2026-10-27
- **Deciders:** Isaac Tumuti

## Context

We planned 16:9 panels (`size: "1792x1024"`). The [Day 2 spikes](../spikes/2026-10-28-findings.md) showed:

- The Responses API `image_generation` tool rejects `1792x1024` (HTTP 400 "unknown value"). `1536x1024` works and returns 1920×1280 (3:2).
- `POST /v1/images/edits` accepts `1792x1024` (returns 2016×1152) but returns no response id, so its images cannot be edited with `previous_response_id`.

Voice edits ("her coat is red now") depend on multi-turn chaining.

## Decision

- Every panel is generated through the **Responses API at `size: "1536x1024"` (3:2)** so it stays editable multi-turn. Each panel revision stores its response id.
- `/v1/images/edits` is used only for **one-off renders** that never need a follow-up edit.
- The animatic and PDF centre-crop or letterbox 3:2 panels to their output format; the panel itself stays 3:2.

## Consequences

- Panels are slightly taller than film frames. Composition prompts should keep key action in the central 16:9 band.
- If Meta adds 16:9 to the Responses tool, only the image adapter and this ADR change.
