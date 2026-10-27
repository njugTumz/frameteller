# ADR 0007: Segment on a downscaled copy

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** Isaac Tumuti

## Context

SAM 3.1 took 7.5–9.5 s per call on full-size 1920×1280 panels, and 2.5–4 s on a 384×256 test image. Click-to-select and pre-segmentation ([ADR 0006](0006-pre-segmentation.md)) both wait on it. Masks are used for selection, canvas cut-outs and edit prompts, so a slightly softer edge is acceptable; a wrong object is not.

## Decision

- `MetaSamAdapter` sends SAM a copy whose **longest side is at most 768 px** (setting `SAM_MAX_SIDE`, default 768; empty means full size).
- Point prompts are scaled down to the copy. Returned masks are scaled back up (bilinear, threshold at half) and their boxes recomputed, so every mask and cut-out the application sees is in full-size panel pixels.

## Evidence

Measured on spike panel A high shot 2 (1920×1280, copy 768×512), one call each:

| Prompt | IoU vs full size | Latency full | Latency 768 |
|---|---|---|---|
| Concept "girl in yellow raincoat" | **0.9956** | 9.5 s | 6.2 s |
| Point click at (972, 645) | **0.9939** | 7.9 s | 4.0 s |

The decision threshold was IoU ≥ 0.95. Cost is unchanged ($0.0025 per image).

## Consequences

- Clicks on uncached objects and background pre-segmentation finish about 3–4 s sooner.
- Mask edges are interpolated from a coarser raster (about 2.5× upscale); thin objects (a cat's tail, a lantern string) may lose detail. If that shows up, raise `SAM_MAX_SIDE` or set it empty for full size.
- One panel and one sample per prompt: re-check on more panels when real projects exist.
