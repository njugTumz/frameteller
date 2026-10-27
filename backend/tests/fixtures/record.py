"""Record the contract-test fixtures once against the real Meta API (costs about $0.04).

    cd backend && .venv/bin/python -m tests.fixtures.record

MODEL_API_KEY comes from .env through the settings class and is never printed. The director runs on the
contributor model, so only the synthetic "Mira and the lantern cat" story is sent. Writes tests/fixtures/meta/.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx2

from frameteller.application.ports import ImageRequest
from frameteller.domain import MediaRef, Point, TranscriptTurn
from frameteller.infrastructure.config import load_settings
from frameteller.infrastructure.local import LocalFileMediaStorage
from frameteller.infrastructure.meta import meta_client
from frameteller.infrastructure.meta.director import MetaSparkDirectorAdapter
from frameteller.infrastructure.meta.image import MetaImageAdapter
from frameteller.infrastructure.meta.sam import MetaSamAdapter
from frameteller.infrastructure.resilience import Breakers, ModelCaller
from tests.builders import project
from tests.fakes import InMemorySpendLedger
from tests.fixtures import META, Scrubber, image

CAP_USD = 0.10
TURN_4 = TranscriptTurn("t4", "Mira smiles and holds out her hand. The cat steps into the light.", 21600, 26800)
PANEL_PROMPT = (
    "Storyboard panel, pencil rough with one accent colour, no text or panel borders. Medium shot. "
    "Mira, an 8-year-old girl in a yellow hooded raincoat and red scarf, kneels in a rainy alley at night "
    "and holds out her hand to a small grey cat with glowing amber eyes under a wooden crate."
)
EDIT_PROMPT = "Make her raincoat and its hood red. Keep everything else the same."


class RecordingTransport(httpx2.AsyncBaseTransport):
    def __init__(self, secret: str) -> None:
        self._inner = httpx2.AsyncHTTPTransport()
        self._secret = secret
        self._scrub = Scrubber()
        self._pending: list[dict[str, Any]] = []

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self._inner.handle_async_request(request)
        raw = await response.aread()
        content_type = response.headers.get("content-type", "application/json")
        text = raw.decode()
        if self._secret in text:
            raise SystemExit("a response contained the API key; nothing written")
        self._pending.append(
            {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "content_type": content_type.split(";")[0],
                "body": self._scrub.body(text, content_type),
            }
        )
        # Re-wrap the already-decoded body without transfer/encoding headers.
        return httpx2.Response(response.status_code, headers={"content-type": content_type}, content=raw)

    def take(self, name: str) -> None:
        META.mkdir(parents=True, exist_ok=True)
        (META / f"{name}.json").write_text(json.dumps(self._pending, indent=1) + "\n")
        print(f"  {name}: {len(self._pending)} exchange(s), status {[e['status'] for e in self._pending]}")
        self._pending = []


async def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="frameteller-record-"))
    settings = load_settings(app_env="local", local_storage_dir=work)
    if settings.director != "muse-spark-1.3-contributor":
        raise SystemExit("record with the contributor director model (synthetic data only)")
    recorder = RecordingTransport(settings.model_api_key.get_secret_value())
    ledger = InMemorySpendLedger()
    caller = ModelCaller(ledger, Breakers())
    storage = LocalFileMediaStorage(work)
    client = meta_client(settings, httpx2.AsyncClient(transport=recorder, timeout=180))

    def spent() -> float:
        total = sum(u.cost_usd for u in ledger.usage)
        if total > CAP_USD:
            raise SystemExit(f"spend cap ${CAP_USD} reached")
        return total

    print("director: one turn")
    director = MetaSparkDirectorAdapter(client, caller, settings)
    p = project(approved=True, shots=0)
    p.add_turn(TURN_4)
    await director.direct_turn(TURN_4, p)
    recorder.take("director_turn")
    spent()

    print("image: draft panel with two references, then a chained edit")
    mira = await storage.put("refs/mira.webp", image("ref_mira.webp"), "image/webp")
    cat = await storage.put("refs/cat.webp", image("ref_cat.webp"), "image/webp")
    images = MetaImageAdapter(client, caller, storage, settings)
    panel = await images.generate(ImageRequest(PANEL_PROMPT, "low", "panel", (mira, cat)), "panels/s1/r1")
    recorder.take("image_generate")
    spent()
    await images.edit(panel.response_id, EDIT_PROMPT, "low", "panels/s1/r2")
    recorder.take("image_edit")
    spent()

    print("sam: concept and point on the small fixture panel")
    small: MediaRef = await storage.put("panels/small.webp", image("panel_small.webp"), "image/webp")
    sam = MetaSamAdapter(client, caller, storage, settings)
    found = await sam.segment_concept(small, "girl in yellow raincoat", "masks/concept")
    recorder.take("sam_concept")
    spent()
    centre = Point(194, 129)
    if found:
        b = found[0].box
        centre = Point((b.left + b.right) // 2, (b.top + b.bottom) // 2)
    await sam.segment_point(small, centre, "masks/point")
    recorder.take("sam_point")

    for u in ledger.usage:
        print(f"  {u.model} {u.operation}: {u.latency_ms} ms, ${u.cost_usd:.4f}, ok={u.ok}")
    print(f"total ${spent():.4f}; concept found {len(found)}; point {centre}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
