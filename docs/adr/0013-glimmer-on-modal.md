# ADR 0013: Muse Glimmer on Modal, with Muse Spark as the fallback reviewer

- **Status:** Accepted
- **Date:** 2026-10-29
- **Deciders:** Isaac Tumuti

## Context

The continuity supervisor ([ADR 0012](0012-continuity-supervisor.md)) reviews every sheet and render. Muse Glimmer is Meta's open-weight model: 30B parameters, Apache 2.0, and it takes images. Self-hosting it gives the reviewer a model we control and a fixed cost per hour instead of per token. Glimmer also counts toward the open-weight bonus. But a self-hosted GPU that scales to zero has a cold start, and a demo cannot wait for it.

## Decision

- **Official release only.** The weights are `meta-models/Muse-Glimmer-30B` on Hugging Face, revision `cec94fcf…` (pinned). The repo is BF16, 59.6 GB and not gated: there is no licence click and no token. The image is Meta's `vllm/vllm-openai:muse-glimmer`, pinned by digest. We serve it with the flags from Meta's vLLM guide (`--reasoning-parser muse_glimmer --generation-config auto`). Sampling comes from the model's own generation config, and reasoning strength is set per request with `chat_template_kwargs`.
- **GPU: one H100 80GB** (USD 3.95/h on Modal).
  - Meta's guide says the BF16 checkpoint needs about 72 GB of VRAM. That rules out 40/48 GB cards.
  - An A100 80GB (USD 2.50/h) would fit with little room for the KV cache of image prompts. It also decodes slower, and a review's answer comes after the model's reasoning.
  - Quantised weights would fit smaller GPUs, but they are not Meta's release.
- **Shape** (`deploy/modal/glimmer.py`):
  - At most 1 container, scaled to zero after 5 idle minutes.
  - Weights cached on the Modal Volume `frameteller-glimmer-weights` (downloaded once on CPU).
  - The OpenAI-compatible endpoint requires a bearer token (`--api-key`). That token is ours, not a Meta key: Modal secret `frameteller-glimmer-token`, GitHub environment secret `GLIMMER_API_KEY`.
- **Fallback** (`REVIEWER=fallback`). `FallbackReviewer` tries Glimmer once with a short timeout (`GLIMMER_TIMEOUT_S`, default 20 s). It falls back to Spark on a timeout (cold start), a 5xx, an open circuit or an unusable answer. Every verdict records the model that served it, and the badge says so ("Checked by Muse Glimmer"). A request to a cold endpoint also starts it, so the next reviews go to Glimmer.
- **Warm before a demo.** `python3 deploy/modal/warm.py --check` wakes the container and waits for it ([runbook](../runbook.md#warm-glimmer-before-a-demo)).

## Consequences

- Measured on 2026-10-29:
  - Cold start: **221 s** from the first request to `/health` = 200 (container start, loading 59.6 GB from the Volume, CUDA graphs).
  - Warm: a short chat answers in 2.1 s, and a reference-sheet review with one image in 6.0 s.
- Cost: an idle-to-idle session (cold start, a few minutes of reviews, 5 minutes of scale-down) is about 15 GPU minutes, about USD 1. Reviews themselves are free per call.
- vLLM's guided decoding for Glimmer leaves out a required array when it would be empty (`issues`). The parser treats a missing `issues` as none found ([FEEDBACK.md](../../FEEDBACK.md)).
- Which reviewer is the default comes from the eval ([supervisor-eval.md](../supervisor-eval.md)), not from preference.
