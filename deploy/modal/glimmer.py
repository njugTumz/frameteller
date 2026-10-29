"""Muse Glimmer on Modal: an OpenAI-compatible vLLM server for the continuity supervisor (ADR 0013).

Meta's official open-weight release (meta-models/Muse-Glimmer-30B, Apache 2.0, ungated), served the way Meta's
vLLM guide shows (https://dev.meta.ai/docs/muse-glimmer/vllm): the official vllm/vllm-openai:muse-glimmer image,
the muse_glimmer reasoning parser and the model's own generation config. Images in, JSON-schema output out.

  modal run deploy/modal/glimmer.py::download   # once: weights into the Volume (CPU only, no GPU time)
  modal deploy deploy/modal/glimmer.py          # the endpoint; scales to zero after 5 idle minutes
  modal app stop frameteller-glimmer            # stop it now (no GPU billed until the next request)

One H100 80 GB: the BF16 weights are about 60 GB and Meta says about 72 GB of VRAM to serve them. Bearer auth is
vLLM's --api-key, from the Modal secret frameteller-glimmer-token (GLIMMER_API_KEY). The token is never printed.
"""

from __future__ import annotations

import os
import subprocess

import modal

APP_NAME = "frameteller-glimmer"
MODEL_REPO = "meta-models/Muse-Glimmer-30B"
MODEL_REVISION = "cec94fcfd6512f2cfe708138c32533b346ea4f69"  # pinned: the release we measured
MODEL_DIR = f"/models/{MODEL_REPO}/{MODEL_REVISION}"
SERVED_NAME = "muse-glimmer"
PORT = 8000

# Meta's image for this model, pinned by digest (the "muse-glimmer" tag on 2026-10-29).
IMAGE = "vllm/vllm-openai:muse-glimmer@sha256:413c8fbecb1204a218117c77a4ea4b3a211d5686ff99c31d82ba6dd0cec8c5a6"

app = modal.App(APP_NAME)
weights = modal.Volume.from_name("frameteller-glimmer-weights", create_if_missing=True)
token = modal.Secret.from_name("frameteller-glimmer-token")  # GLIMMER_API_KEY

image = (
    # The image ships python3 only; Modal looks for `python` to run our functions.
    modal.Image.from_registry(IMAGE, setup_dockerfile_commands=["RUN ln -sf \"$(command -v python3)\" /usr/local/bin/python"])
    .entrypoint([])  # the image's entrypoint is `vllm serve`; Modal runs our function instead
    .env({"HF_HUB_DISABLE_TELEMETRY": "1", "VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1"})
)


@app.function(image=image, volumes={"/models": weights}, cpu=4, memory=8192, timeout=3600)
def download() -> None:
    """Copy the pinned weights from Hugging Face into the Volume. Runs on CPU; safe to re-run (it resumes)."""
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL_REPO, revision=MODEL_REVISION, local_dir=MODEL_DIR, max_workers=16)
    weights.commit()
    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, files in os.walk(MODEL_DIR) for f in files)
    print(f"{MODEL_REPO}@{MODEL_REVISION[:7]}: {total / 1e9:.1f} GB in the volume")


@app.function(
    image=image,
    gpu="H100",
    volumes={"/models": weights},
    secrets=[token],
    max_containers=1,  # one GPU at most: the budget, and reviews are a trickle
    scaledown_window=5 * 60,  # scale to zero after 5 idle minutes
    timeout=24 * 3600,
)
@modal.concurrent(max_inputs=16)
@modal.web_server(port=PORT, startup_timeout=20 * 60)
def serve() -> None:
    subprocess.Popen(
        [
            "vllm",
            "serve",
            MODEL_DIR,
            "--served-model-name", SERVED_NAME,
            "--host", "0.0.0.0",
            "--port", str(PORT),
            "--api-key", os.environ["GLIMMER_API_KEY"],  # bearer auth on every /v1 route
            "--reasoning-parser", "muse_glimmer",  # reasoning stays out of the JSON content
            "--generation-config", "auto",  # Meta's sampling: temperature 1.0, top_p 0.95, top_k 64
            "--max-model-len", "32768",  # a panel and up to three reference sheets, plus the rubric
            "--limit-mm-per-prompt", '{"image": 5}',
            "--gpu-memory-utilization", "0.92",
            "--max-num-seqs", "16",
            # vLLM does not log request contents by default: prompts and images never reach the logs.
        ]
    )  # fmt: skip
