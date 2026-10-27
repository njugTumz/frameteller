"""Recorded Meta API exchanges for adapter contract tests, and the scrubbing used when recording them.

Each `meta/<name>.json` is a list of exchanges recorded once by `record.py` against the real API:
ids replaced by stable placeholders, key-like strings removed, images shrunk to thumbnails. Request
bodies are not kept (they hold image data); contract tests assert on the requests they make instead.
"""

from __future__ import annotations

import base64
import io
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
from PIL import Image

HERE = Path(__file__).parent
META = HERE / "meta"
IMAGES = HERE / "images"

KEY_LIKE = re.compile(r"\b(?:LLM_|sk-)[A-Za-z0-9_\-]{8,}")
ID_FIELDS = {"id", "response_id", "previous_response_id", "item_id", "system_fingerprint", "sessionId"}
IMAGE_FIELDS = {"result", "partial_image_b64", "b64_json"}
THUMBNAIL = (48, 32)


def image(name: str) -> bytes:
    return (IMAGES / name).read_bytes()


def thumbnail_b64(b64: str) -> str:
    with Image.open(io.BytesIO(base64.b64decode(b64))) as im:
        small = im.convert("RGB").resize(THUMBNAIL)
    buf = io.BytesIO()
    small.save(buf, "WEBP", quality=60)
    return base64.b64encode(buf.getvalue()).decode()


class Scrubber:
    """Stable placeholders, so an id seen in two recordings (an edit's previous_response_id) still matches."""

    def __init__(self) -> None:
        self.ids: dict[str, str] = {}

    def placeholder(self, value: str) -> str:
        if value not in self.ids:
            prefix = value.split("_", 1)[0] + "_" if "_" in value else ""
            self.ids[value] = f"{prefix}fixture{len(self.ids) + 1}"
        return self.ids[value]

    def value(self, obj: Any, key: str = "") -> Any:
        if isinstance(obj, dict):
            return {k: self.value(v, k) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.value(v, key) for v in obj]
        if isinstance(obj, str):
            if key in IMAGE_FIELDS and len(obj) > 1000:
                return thumbnail_b64(obj)
            if key in ID_FIELDS and obj:
                return self.placeholder(obj)
            return KEY_LIKE.sub("[scrubbed]", obj)
        return obj

    def body(self, text: str, content_type: str) -> str:
        if "event-stream" in content_type:
            lines = []
            for line in text.splitlines():
                if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
                    line = "data: " + json.dumps(self.value(json.loads(line[5:])), separators=(",", ":"))
                lines.append(KEY_LIKE.sub("[scrubbed]", line))
            return "\n".join(lines) + "\n"
        try:
            return json.dumps(self.value(json.loads(text)), indent=1)
        except json.JSONDecodeError:
            return KEY_LIKE.sub("[scrubbed]", text)


def load(name: str) -> list[dict[str, Any]]:
    exchanges: list[dict[str, Any]] = json.loads((META / f"{name}.json").read_text())
    return exchanges


Check = Callable[[httpx2.Request], None]


def replay(
    exchanges: str | list[dict[str, Any]], check: Check | None = None
) -> tuple[httpx2.MockTransport, list[httpx2.Request]]:
    """A transport that answers each request with the next exchange (a fixture name or a list) and keeps requests."""
    name = exchanges if isinstance(exchanges, str) else "exchanges"
    queue = load(exchanges) if isinstance(exchanges, str) else list(exchanges)
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if not queue:
            raise AssertionError(f"{name}: more requests than recorded exchanges")
        ex = queue.pop(0)
        if (request.method, request.url.path) != (ex["method"], ex["path"]):
            raise AssertionError(
                f"{name}: expected {ex['method']} {ex['path']}, got {request.method} {request.url.path}"
            )
        seen.append(request)
        if check is not None:
            check(request)
        return httpx2.Response(ex["status"], headers={"content-type": ex["content_type"]}, text=ex["body"])

    return httpx2.MockTransport(handler), seen
