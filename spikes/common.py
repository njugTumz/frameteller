"""Shared helpers for the Day 2 spikes: client, timing, cost log, budget guard.

Spikes are throwaway scripts that prove the risky parts of the pipeline. They are
not app code and must not be imported from backend/ or frontend/.
"""

from __future__ import annotations

import base64
import io
import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

ROOT = Path(__file__).resolve().parent.parent
SPIKES = ROOT / "spikes"
FIXTURES = SPIKES / "fixtures"
OUT = SPIKES / "out"
COSTS = OUT / "costs.jsonl"

BASE_URL = "https://api.meta.ai/v1"
BUDGET_USD = 2.00

# USD. Token prices are per 1M tokens.
PRICE_IMAGE = 0.01
PRICE_SAM_IMAGE = 2.50 / 1000
PRICE_SPARK_CONTRIB = {"input": 0.10, "cached": 0.002, "output": 0.20}
PRICE_ASR_PER_HOUR = 0.18

TEXT_MODEL = "muse-spark-1.3-contributor"  # synthetic story only (CLAUDE.md section 5)
IMAGE_MODEL = "muse-image-1.0"
SAM_MODEL = "sam-3.1"
ASR_MODEL = "muse-voice-transcribe-1.0"

OUT.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    pass


def api_key() -> str:
    """Read MODEL_API_KEY from the repo .env. The value is never printed or logged."""
    load_dotenv(ROOT / ".env")
    key = os.environ.get("MODEL_API_KEY", "").strip()
    if not key:
        raise SystemExit("MODEL_API_KEY is not set. Add it to .env in the repo root.")
    return key


def client() -> OpenAI:
    return OpenAI(api_key=api_key(), base_url=BASE_URL, timeout=300, max_retries=3)


def async_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key(), base_url=BASE_URL, timeout=300, max_retries=3)


@dataclass
class Timer:
    started: float = field(default_factory=time.perf_counter)
    seconds: float = 0.0


@contextmanager
def timed() -> Iterator[Timer]:
    t = Timer()
    try:
        yield t
    finally:
        t.seconds = time.perf_counter() - t.started


def spent() -> float:
    if not COSTS.exists():
        return 0.0
    return sum(json.loads(line)["cost_usd"] for line in COSTS.read_text().splitlines() if line.strip())


def reserve(expected_usd: float) -> None:
    """Refuse a call that would take total spend past the budget."""
    with _lock:
        total = spent()
        if total + expected_usd > BUDGET_USD:
            raise BudgetExceeded(f"spent ${total:.4f}; next call (${expected_usd:.4f}) would exceed ${BUDGET_USD:.2f}")


def log_cost(
    *,
    spike: str,
    model: str,
    latency_s: float,
    cost_usd: float,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_tokens: int | None = None,
    note: str = "",
) -> None:
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "spike": spike,
        "model": model,
        "latency_s": round(latency_s, 3),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "cost_usd": round(cost_usd, 6),
        "note": note,
    }
    with _lock, COSTS.open("a") as f:
        f.write(json.dumps(row) + "\n")


def usage_of(response: Any) -> tuple[int | None, int | None, int | None]:
    u = getattr(response, "usage", None)
    if u is None:
        return None, None, None
    details = getattr(u, "input_tokens_details", None)
    cached = getattr(details, "cached_tokens", None) if details is not None else None
    return getattr(u, "input_tokens", None), getattr(u, "output_tokens", None), cached


def spark_cost(input_tokens: int | None, output_tokens: int | None, cached_tokens: int | None) -> float:
    i, o, c = input_tokens or 0, output_tokens or 0, cached_tokens or 0
    p = PRICE_SPARK_CONTRIB
    return ((i - c) * p["input"] + c * p["cached"] + o * p["output"]) / 1_000_000


def image_tool(size: str, strength: str) -> dict[str, Any]:
    # enable_image_search stays false: no real likenesses or copyrighted designs.
    return {
        "type": "image_generation",
        "enable_image_search": False,
        "enable_web_search": False,
        "enable_shell": False,
        "reasoning_strength": strength,
        "size": size,
    }


def image_from_response(response: Any) -> bytes:
    for item in response.output:
        if getattr(item, "type", None) == "image_generation_call" and getattr(item, "result", None):
            return base64.b64decode(item.result)
    raise RuntimeError(f"no image in response {getattr(response, 'id', '?')}")


def data_url(path: Path) -> str:
    from PIL import Image

    fmt = (Image.open(path).format or "PNG").lower()
    return f"data:image/{fmt};base64," + base64.b64encode(path.read_bytes()).decode()


def save_image(raw: bytes, stem: Path) -> Path:
    """Save image bytes with the extension of their real format."""
    from PIL import Image

    fmt = (Image.open(io.BytesIO(raw)).format or "PNG").lower()
    path = stem.with_suffix("." + ("jpg" if fmt == "jpeg" else fmt))
    path.write_bytes(raw)
    return path


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
