# Feedback log

Running notes for the optional feedback fields in the submission. Whenever something about a Meta model, the docs, or a partner is confusing, slow or great, add a one-line entry. Concrete details (endpoint, error text, latency, what we expected) make the feedback useful.

**Format:** newest first, one line each.

```
- YYYY-MM-DD · <product> · <good | issue | idea> · what happened, and what we expected
```

## Meta products

- 2026-10-27 · Model API · good · GET /v1/models works with the key and lists all hosted models, including Contributor variants.
- 2026-10-27 · muse-image-1.0 docs · issue · The images guide's mask parameter section is cut off mid-sentence; masked edits appear unsupported, which changed our SAM edit design.

<!-- e.g. - 2026-10-28 · muse-image-1.0 · issue · /v1/images/edits rejected a PNG mask with 400 "invalid_mask"; docs don't list mask format. -->

## Partner technologies: Fireworks, Modal, Baseten

<!-- e.g. - 2026-11-01 · Modal · good · Glimmer cold start on a single GPU was ~40 s. -->
