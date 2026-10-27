# Feedback log

Running notes for the optional feedback fields in the submission. Whenever something about a Meta model, the docs, or a partner is confusing, slow or great, add a one-line entry. Concrete details (endpoint, error text, latency, what we expected) make the feedback useful.

**Format:** newest first, one line each.

```
- YYYY-MM-DD · <product> · <good | issue | idea> · what happened, and what we expected
```

## Meta products

- 2026-10-27 · muse-voice-transcribe-1.0 · good · The realtime WebSocket worked first time from the documented protocol: a 48.5 s narration streamed at real time closed cleanly with code 1000 about 2 s after the audio ended, for $0.0024.
- 2026-10-27 · muse-image-1.0 · good · Prompt caching applies to image requests: a panel request with two reference images reported 3,968 of 4,364 input tokens cached, and a chained edit 4,352. Worth stating in the image docs.
- 2026-10-27 · sam-3.1 · good · Point selection on a 384×256 image took 2.5–2.9 s, against ~7.5 s at 1920×1280. A note on input size versus latency would help.
- 2026-10-27 · muse-image-1.0 · issue · The Responses `image_generation` tool rejects `size: "1792x1024"` with 400 "unknown value" (also `16:9`, `1920x1080`), while `/v1/images/edits` accepts it. The error does not list allowed values; we found `1536x1024` by trial.
- 2026-10-27 · muse-image-1.0 · good · Reference sheets as `input_image` kept two characters on model across 18 panels, at 15–25 s per image. It even faithfully carried a detail the reference sheet invented.
- 2026-10-27 · muse-image-1.0 · idea · `/v1/images/edits` returns only `b64_json`, no response id, so its images cannot continue as a `previous_response_id` edit chain. Returning one would let us use it for native 16:9 panels.
- 2026-10-27 · muse-image-1.0 · issue · "Make her raincoat red" recoloured the coat but left the hood yellow, and "make her larger" grew her by only 3%. Layout outside the subject stayed stable.
- 2026-10-27 · sam-3.1 · good · `meta_sam_parser` worked first time: point prompt via `build_object_prompt`, stream parsing and mask decoding with no diagnostics, about 7.5 s per call. A single click gave a clean full-body mask.
- 2026-10-27 · muse-spark-1.3-contributor · issue · An identical ~1k-token request sent twice reported `cached_tokens: 0`. The docs could state the minimum cacheable prefix length.
- 2026-10-27 · Model API · good · GET /v1/models works with the key and lists all hosted models, including Contributor variants.
- 2026-10-27 · muse-image-1.0 docs · issue · The images guide's mask parameter section is cut off mid-sentence; masked edits appear unsupported, which changed our SAM edit design.

<!-- e.g. - 2026-10-28 · muse-image-1.0 · issue · /v1/images/edits rejected a PNG mask with 400 "invalid_mask"; docs don't list mask format. -->

## Partner technologies: Fireworks, Modal, Baseten

<!-- e.g. - 2026-11-01 · Modal · good · Glimmer cold start on a single GPU was ~40 s. -->
