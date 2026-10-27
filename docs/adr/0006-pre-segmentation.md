# ADR 0006: Pre-segment characters after each panel renders

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** Isaac Tumuti

## Context

In the [Day 2 spikes](../spikes/2026-10-28-findings.md), one SAM 3.1 call took about 7.5 s. Waiting that long after a click breaks the "click to select" moment. We already know who is in each panel: the shot's `character_ids` from the director. SAM costs $0.0025 per image.

## Decision

- After a panel revision renders, a **background job** segments each character in the shot with a concept prompt built from the character's name and short description, and caches the masks against that panel revision.
- A click first checks the cached masks for that revision. If a mask contains the point, it is returned **without calling SAM**.
- Only clicks on uncached objects (props, background) call SAM with a point prompt.
- A new panel revision invalidates its masks and triggers pre-segmentation again.

## Consequences

- Clicking a character feels instant.
- Costs about $0.0025 per character per panel revision, even if the user never clicks. The budget guard counts it.
