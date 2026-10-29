"""Run a reviewer over the labelled eval set and score it (docs/supervisor-eval.md). Spends real credits.

    cd backend && .venv/bin/python -m tests.eval.run_eval spark      # muse-spark-1.3, about $0.10
    cd backend && .venv/bin/python -m tests.eval.run_eval glimmer    # our Modal endpoint: warm it first
    cd backend && .venv/bin/python -m tests.eval.run_eval screen     # both, combined: no calls

Each item is reviewed once, in order, with the same rubrics, prompt and schema the supervisor uses. A sheet
is checked against cast.md; a panel against panel-continuity.md and shot.md with its shot and the clean
reference sheets. Scores count only blocker and major issues, as the policy does:
- a flagged item is one with any blocker or major issue; precision and recall are over flagged items;
- rule hits: of the items with a known failure, how many name one of the expected rules;
- false fix: a clean item the reviewer would have edited by itself (decision fix on a draft).
Writes tests/eval/results-<reviewer>.json. MODEL_API_KEY comes from .env through the settings class and the
Glimmer token from GLIMMER_API_KEY or ~/.config/frameteller/glimmer.token; neither is printed.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from tests.fakes import InMemorySpendLedger

from frameteller.application.ports import ReferenceSheet, ReviewerPort, ReviewRequest
from frameteller.application.rubrics import RubricSet
from frameteller.domain import Decision, Framing, MediaRef, PanelStyle, Shot
from frameteller.infrastructure.config import load_settings
from frameteller.infrastructure.meta import meta_client
from frameteller.infrastructure.resilience import Breakers, ModelCaller, RetryPolicy
from frameteller.infrastructure.review import FileRubricLibrary, GlimmerReviewerAdapter, SparkReviewerAdapter

HERE = Path(__file__).parent
AGENTS = HERE.parents[2] / "agents"
GLIMMER_URL = "https://geoftums--frameteller-glimmer-serve.us-east.modal.run/v1"
TOKEN_FILE = Path.home() / ".config" / "frameteller" / "glimmer.token"
CAP_USD = 0.30


class FolderStorage:
    """MediaStoragePort.get over tests/eval/images (read only)."""

    async def get(self, ref: MediaRef) -> bytes:
        return (HERE / "images" / ref.key).read_bytes()


def reviewer(name: str, caller: ModelCaller) -> ReviewerPort:
    storage = FolderStorage()
    if name == "spark":
        settings = load_settings(app_env="local", director_model="muse-spark-1.3")
        return SparkReviewerAdapter(meta_client(settings), caller, storage, "muse-spark-1.3", RetryPolicy(2, 120))  # type: ignore[arg-type]
    token = os.environ.get("GLIMMER_API_KEY") or TOKEN_FILE.read_text().strip()
    client = AsyncOpenAI(base_url=GLIMMER_URL, api_key=token, max_retries=0)
    return GlimmerReviewerAdapter(client, caller, storage, "muse-glimmer", RetryPolicy(2, 120))  # type: ignore[arg-type]


def request_for(item: dict[str, Any], labels: dict[str, Any], rubrics: FileRubricLibrary) -> ReviewRequest:
    characters = labels["characters"]
    if item["kind"] == "sheet":
        c = characters[item["character"]]
        return ReviewRequest(
            images=(MediaRef(item["image"]),),
            rubric=RubricSet((rubrics.get("cast"),)),
            style=PanelStyle(labels["style"]),
            subject=f"{c['name']}: {c['description']}",
        )
    s = labels["shots"][str(item["shot"])]
    shot = Shot(
        id=f"s{item['shot']}",
        number=item["shot"],
        framing=Framing(s["framing"]),
        character_ids=tuple(s["characters"]),
        setting=s["setting"],
        action=s["action"],
        dialogue="",
        source_turn_ids=("t1",),
        duration_ms=4000,
    )
    sheets = tuple(
        ReferenceSheet(characters[cid]["name"], characters[cid]["description"], MediaRef(f"sheet-{cid}.webp"))
        for cid in s["characters"]
    )
    return ReviewRequest(
        images=(MediaRef(item["image"]),),
        rubric=RubricSet((rubrics.get("panel-continuity"), rubrics.get("shot"))),
        style=PanelStyle(labels["style"]),
        reference_sheets=sheets,
        shot=shot,
    )


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if "error" not in r]
    bad = [r for r in ok if r["expected_rules"]]
    clean = [r for r in ok if not r["expected_rules"]]
    flagged = [r for r in ok if r["serious"]]
    tp = [r for r in bad if r["serious"]]
    hits = [r for r in bad if set(r["serious"]) & set(r["expected_rules"])]
    latencies = [r["latency_ms"] for r in ok]
    costs = [r["cost_usd"] for r in ok]
    return {
        "items": len(rows),
        "errors": len(rows) - len(ok),
        "precision": round(len(tp) / len(flagged), 2) if flagged else None,
        "recall": round(len(tp) / len(bad), 2) if bad else None,
        "rule_hits": f"{len(hits)}/{len(bad)}",
        "false_flags": f"{len([r for r in clean if r['serious']])}/{len(clean)}",
        "false_fixes": f"{len([r for r in clean if r['decision'] == 'fix'])}/{len(clean)}",
        "fix_when_fixable": f"{len([r for r in bad if r['fixable'] and r['decision'] == 'fix'])}"
        f"/{len([r for r in bad if r['fixable']])}",
        "median_latency_ms": round(statistics.median(latencies)) if latencies else None,
        "cost_per_review_usd": round(sum(costs) / len(costs), 5) if costs else None,
    }


def screen() -> None:
    """REVIEWER=screen from the two recorded runs, no calls: Glimmer's passes stand, Spark decides its flags."""
    glimmer = json.loads((HERE / "results-glimmer.json").read_text())["rows"]
    spark = {r["image"]: r for r in json.loads((HERE / "results-spark.json").read_text())["rows"]}
    rows = []
    for g in glimmer:
        if g.get("decision") == "pass":
            rows.append(g)
        else:
            s = spark[g["image"]]
            rows.append(s | {"latency_ms": g["latency_ms"] + s["latency_ms"]})  # one after the other
    summary = score(rows)
    out = {"reviewer": "screen", "summary": summary, "spark_share": f"{len(rows) - sum(r in glimmer for r in rows)}"}
    out["rows"] = rows
    (HERE / "results-screen.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(summary, indent=1), f"\nreviews sent on to Spark: {out['spark_share']}/{len(rows)}")


async def main(name: str) -> None:
    labels = json.loads((HERE / "labels.json").read_text())
    ledger = InMemorySpendLedger()
    caller = ModelCaller(ledger, Breakers(10, 30))
    port = reviewer(name, caller)
    rubrics = FileRubricLibrary(AGENTS)
    rows: list[dict[str, Any]] = []
    for item in labels["items"]:
        spent = sum(u.cost_usd for u in ledger.usage)
        if spent > CAP_USD:
            raise SystemExit(f"spend cap ${CAP_USD} reached")
        before = len(ledger.usage)
        row: dict[str, Any] = {
            "image": item["image"],
            "expected_rules": item["rules"],
            "fixable": item.get("fixable", False),
        }
        started = time.perf_counter()
        try:
            v = await port.review(request_for(item, labels, rubrics))
        except Exception as e:
            row |= {"error": type(e).__name__, "latency_ms": round((time.perf_counter() - started) * 1000)}
        else:
            row |= {
                "decision": v.decision.value,
                "confidence": v.confidence,
                "serious": [i.rule_id for i in v.serious_issues],
                "minor": [i.rule_id for i in v.issues if not i.serious],
                "issues": [f"{i.rule_id}: {i.description}" for i in v.issues],
                "fix": v.fix_instruction if v.decision is Decision.FIX else "",
                "latency_ms": v.latency_ms,
            }
        row["cost_usd"] = round(sum(u.cost_usd for u in ledger.usage[before:]), 6)
        rows.append(row)
        mark = "ok " if bool(row.get("serious")) == bool(item["rules"]) else "MISS"
        print(f"{mark} {item['image']:28} {row.get('decision', row.get('error'))} {row.get('serious', '')}", flush=True)
    summary = score(rows)
    out = {"reviewer": name, "summary": summary, "rows": rows}
    (HERE / f"results-{name}.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    print(f"total ${sum(u.cost_usd for u in ledger.usage):.4f}")


if __name__ == "__main__":
    if sys.argv[1:] == ["screen"]:
        screen()
    else:
        asyncio.run(main(sys.argv[1] if sys.argv[1:] else "spark"))
