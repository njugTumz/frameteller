"""The lighthouse story end to end with the continuity supervisor on. Spends real credits (about $0.25).

    python3 ../deploy/modal/warm.py && cd backend && .venv/bin/python scripts/lighthouse_supervised.py

The six paragraphs of spikes/fixtures/lighthouse.txt become six synthetic turns through the paid director, as in
lighthouse_cast.py. The real composition root does the rest: reference sheets (each reviewed against cast.md),
cast approval, a draft per shot (each reviewed and, where it can, fixed), then finals of shots 4 and 5 (reviewed,
never changed). The reviewer is REVIEWER (default screen: Muse Glimmer on our Modal endpoint, Muse Spark
confirming whatever it flags). Prints every supervisor decision and the spend per model. Storage is local,
under spikes/out/lighthouse-supervised. Keys come from .env (settings) and ~/.config/frameteller/glimmer.token;
neither is printed.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import Counter
from pathlib import Path

from frameteller.application.use_cases import DirectTurn
from frameteller.domain import PanelStyle, TranscriptTurn
from frameteller.infrastructure.config import load_settings
from frameteller.infrastructure.local import FileSpendLedger, JsonFileProjectRepository
from frameteller.infrastructure.meta import meta_client
from frameteller.infrastructure.meta.director import MetaSparkDirectorAdapter
from frameteller.infrastructure.resilience import Breakers, ModelCaller
from frameteller.infrastructure.system import RandomIds
from frameteller.interface.container import build_container

ROOT = Path(__file__).resolve().parents[2]
STORY = ROOT / "spikes" / "fixtures" / "lighthouse.txt"
OUT = ROOT / "spikes" / "out" / "lighthouse-supervised"
GLIMMER_URL = "https://geoftums--frameteller-glimmer-serve.us-east.modal.run/v1"
TOKEN_FILE = Path.home() / ".config" / "frameteller" / "glimmer.token"
TURN_MS = 6000
FINALS = (4, 5)
T0 = time.perf_counter()


def say(message: str) -> None:
    print(f"[{time.perf_counter() - T0:6.1f}s] {message}", flush=True)


async def main() -> None:
    os.environ.setdefault("DIRECTOR_MODEL", "muse-spark-1.3")
    reviewer = os.environ.get("REVIEWER", "screen")
    glimmer: dict[str, object] = {}
    if reviewer != "spark":
        glimmer = {"glimmer_base_url": GLIMMER_URL, "glimmer_api_key": TOKEN_FILE.read_text().strip()}
    settings = load_settings(storage_backend="local", local_storage_dir=OUT / "store", reviewer=reviewer, **glimmer)
    if settings.director.endswith("-contributor"):
        raise SystemExit("Use the paid director for the user's story: DIRECTOR_MODEL=muse-spark-1.3")
    c = build_container(settings)
    if c.glimmer_lease:
        await c.glimmer_lease.grant(30)  # warmed by deploy/modal/warm.py just before this run
    ledger = FileSpendLedger(settings.local_storage_dir)
    director = MetaSparkDirectorAdapter(meta_client(settings), ModelCaller(ledger, Breakers()), settings)
    direct = DirectTurn(JsonFileProjectRepository(settings.local_storage_dir), director, RandomIds())

    paragraphs = [p.strip() for p in STORY.read_text("utf-8").splitlines() if p.strip()]
    pid = (await c.create_project.execute("The Lighthouse", PanelStyle.PENCIL)).id
    say(f"project {pid}, director {settings.director}, reviewer {reviewer}")
    for i, text in enumerate(paragraphs, start=1):
        await direct.execute(pid, TranscriptTurn(f"lighthouse-b{i}", text, (i - 1) * TURN_MS, i * TURN_MS))
    project = await c.get_project.execute(pid)
    say(f"{len(project.shots)} shots; cast {list(project.bible.characters)}")

    await c.request_cast.execute(pid, list(project.bible.characters))
    await c.jobs.join()  # sheets, then their reviews
    say(f"cast approved: {(await c.approve_cast.execute(pid)).approved}")
    for shot in (await c.get_project.execute(pid)).shots:
        await c.request_render.execute(pid, shot.id, "low")
    await c.jobs.join()  # drafts, pre-segmentation, reviews and fixes
    say("drafts drawn and supervised")
    project = await c.get_project.execute(pid)
    for shot in project.shots:
        if shot.number in FINALS:
            await c.request_render.execute(pid, shot.id, "high")
    await c.jobs.join()
    say("finals drawn and supervised")

    project = await c.get_project.execute(pid)
    print("\nSupervisor decisions, in order:")
    for e in project.supervisor_log:
        print(f"- [{e.outcome.value}] ({e.model}) {e.message}")
    print("\nBadges:")
    for shot in project.shots:
        review = project.panel(shot.id).review
        badge = f"{review.summary} ({review.verdict.model})" if review else "no review"
        print(f"- shot {shot.number} r{project.panel(shot.id).revision}: {badge}")
    # The store is this run's own (a new folder per run), so every usage line in it is this run's.
    lines = (OUT / "store" / "spend.jsonl").read_text().splitlines()
    usage = [u for u in map(json.loads, lines) if u.get("type") == "usage"]
    by_model: Counter[str] = Counter()
    calls: Counter[str] = Counter()
    for u in usage:
        by_model[u["model"]] += u.get("cost_usd", 0.0)
        calls[f"{u['model']} {u['operation']}"] += 1
    print("\nCalls:", dict(calls))
    print("Spend by model:", {m: round(v, 4) for m, v in by_model.items()})
    say(f"total ${sum(by_model.values()):.4f}")


if __name__ == "__main__":
    asyncio.run(main())
