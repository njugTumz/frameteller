"""Record the reviewer contract fixtures once: Muse Spark (contributor model) and our Muse Glimmer endpoint.

    cd backend && .venv/bin/python -m tests.fixtures.record_review

Both review the synthetic "Mira and the lantern cat" fixture panel against Mira's fixture sheet, so only
synthetic data is sent (CLAUDE.md section 5). Costs about $0.001 on Meta; warm Glimmer first
(deploy/modal/warm.py). MODEL_API_KEY comes from .env through the settings class and the Glimmer token from
~/.config/frameteller/glimmer.token; neither is printed or written. Writes tests/fixtures/meta/review_*.json.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx2
from openai import AsyncOpenAI

from frameteller.application.ports import ReferenceSheet, ReviewRequest
from frameteller.application.rubrics import RubricSet
from frameteller.domain import PanelStyle
from frameteller.infrastructure.config import load_settings
from frameteller.infrastructure.local import LocalFileMediaStorage
from frameteller.infrastructure.meta import meta_client
from frameteller.infrastructure.resilience import Breakers, ModelCaller, RetryPolicy
from frameteller.infrastructure.review import FileRubricLibrary, GlimmerReviewerAdapter, SparkReviewerAdapter
from tests.builders import project
from tests.fakes import InMemorySpendLedger
from tests.fixtures import image
from tests.fixtures.record import RecordingTransport

AGENTS = Path(__file__).resolve().parents[3] / "agents"
GLIMMER_URL = "https://geoftums--frameteller-glimmer-serve.us-east.modal.run/v1"
TOKEN_FILE = Path.home() / ".config" / "frameteller" / "glimmer.token"


async def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="frameteller-record-"))
    settings = load_settings(app_env="local", local_storage_dir=work)
    if settings.director != "muse-spark-1.3-contributor":
        raise SystemExit("record with the contributor director model (synthetic data only)")
    storage = LocalFileMediaStorage(work)
    mira = await storage.put("refs/mira.webp", image("ref_mira.webp"), "image/webp")
    panel = await storage.put("panels/small.webp", image("panel_small.webp"), "image/webp")
    p = project(approved=True, shots=1)
    rubrics = FileRubricLibrary(AGENTS)
    request = ReviewRequest(
        images=(panel,),
        rubric=RubricSet((rubrics.get("panel-continuity"), rubrics.get("shot"))),
        style=PanelStyle.PENCIL,
        reference_sheets=(ReferenceSheet("Mira", p.bible.get("mira").canonical_description, mira),),
        shot=p.shot("s1"),
    )
    ledger = InMemorySpendLedger()
    caller = ModelCaller(ledger, Breakers())
    policy = RetryPolicy(1, 180)

    spark_rec = RecordingTransport(settings.model_api_key.get_secret_value())
    spark_client = meta_client(settings, httpx2.AsyncClient(transport=spark_rec, timeout=180))
    v = await SparkReviewerAdapter(spark_client, caller, storage, settings.director, policy).review(request)
    spark_rec.take("review_spark")
    print(f"  spark: {v.decision.value} {[i.rule_id for i in v.issues]} {v.latency_ms} ms")

    token = TOKEN_FILE.read_text().strip()
    glimmer_rec = RecordingTransport(token)
    glimmer_client = AsyncOpenAI(
        base_url=GLIMMER_URL,
        api_key=token,
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=glimmer_rec, timeout=180),
    )
    v = await GlimmerReviewerAdapter(glimmer_client, caller, storage, "muse-glimmer", policy).review(request)
    glimmer_rec.take("review_glimmer")
    print(f"  glimmer: {v.decision.value} {[i.rule_id for i in v.issues]} {v.latency_ms} ms")
    print(f"  total ${sum(u.cost_usd for u in ledger.usage):.4f}")


if __name__ == "__main__":
    asyncio.run(main())
