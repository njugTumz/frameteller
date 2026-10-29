"""Reviewer adapters against recorded answers: Muse Spark on Meta's API, Muse Glimmer on our vLLM endpoint."""

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest
from openai import AsyncOpenAI

from frameteller.application.errors import InvalidModelOutputError
from frameteller.application.ports import ReferenceSheet, ReviewRequest
from frameteller.application.rubrics import RubricSet
from frameteller.domain import Decision, PanelStyle, Severity
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.local import LocalFileMediaStorage
from frameteller.infrastructure.meta import meta_client
from frameteller.infrastructure.resilience import ModelCaller, RetryPolicy
from frameteller.infrastructure.review import FileRubricLibrary, GlimmerReviewerAdapter, SparkReviewerAdapter
from frameteller.infrastructure.review.reviewer import ANSWER_SHAPE, REVIEW_PROMPT
from tests.builders import project
from tests.fakes import InMemorySpendLedger
from tests.fixtures import image, load, replay

AGENTS = Path(__file__).resolve().parents[3] / "agents"
POLICY = RetryPolicy(1, 30)


async def review_request(storage: LocalFileMediaStorage) -> ReviewRequest:
    mira = await storage.put("refs/mira.webp", image("ref_mira.webp"), "image/webp")
    panel = await storage.put("panels/small.webp", image("panel_small.webp"), "image/webp")
    p = project(approved=True, shots=1)
    rubrics = FileRubricLibrary(AGENTS)
    return ReviewRequest(
        images=(panel,),
        rubric=RubricSet((rubrics.get("panel-continuity"), rubrics.get("shot"))),
        style=PanelStyle.PENCIL,
        reference_sheets=(ReferenceSheet("Mira", p.bible.get("mira").canonical_description, mira),),
        shot=p.shot("s1"),
    )


def body(request: httpx2.Request) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(request.content)
    return data


def answering(name: str, content: str) -> list[dict[str, Any]]:
    """The recorded exchange with a different model answer."""
    ex = load(name)[0]
    b = json.loads(ex["body"])
    b["choices"][0]["message"]["content"] = content
    return [{**ex, "body": json.dumps(b)}]


def glimmer_client(transport: httpx2.MockTransport) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url="https://glimmer.test/v1",
        api_key="test-endpoint-token",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=transport),
    )


async def test_spark_reviews_with_images_a_strict_schema_and_low_effort(
    settings: Settings, caller: ModelCaller, storage: LocalFileMediaStorage, ledger: InMemorySpendLedger
) -> None:
    transport, seen = replay("review_spark")
    client = meta_client(settings, httpx2.AsyncClient(transport=transport))
    reviewer = SparkReviewerAdapter(client, caller, storage, "muse-spark-1.3-contributor", POLICY)

    v = await reviewer.review(await review_request(storage))

    assert v.decision is Decision.PASS
    assert v.issues == ()
    assert v.model == "muse-spark-1.3-contributor"
    assert dict(v.rubrics).keys() == {"panel-continuity", "shot"}
    sent = body(seen[0])
    assert sent["reasoning_effort"] == "low"
    schema = sent["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert "CONT-04" in schema["schema"]["properties"]["issues"]["items"]["properties"]["rule_id"]["enum"]
    assert sent["messages"][0] == {"role": "system", "content": REVIEW_PROMPT}  # the stable, cacheable prefix
    images = [p for p in sent["messages"][2]["content"] if p["type"] == "image_url"]
    assert len(images) == 2  # Mira's sheet, then the panel
    assert all(p["image_url"]["url"].startswith("data:image/webp;base64,") for p in images)
    [usage] = ledger.usage
    assert (usage.operation, usage.input_tokens) == ("review", 1355)
    assert usage.cost_usd > 0


async def test_glimmer_reviews_with_reasoning_strength_and_the_answer_shape_spelled_out(
    caller: ModelCaller, storage: LocalFileMediaStorage, ledger: InMemorySpendLedger
) -> None:
    transport, seen = replay("review_glimmer")
    reviewer = GlimmerReviewerAdapter(glimmer_client(transport), caller, storage, "muse-glimmer", POLICY)

    v = await reviewer.review(await review_request(storage))

    # Recorded before the shape was spelled out: "ask" with the issues left out parses as no issues found.
    assert v.decision is Decision.ASK
    assert v.issues == ()
    assert v.model == "muse-glimmer"
    sent = body(seen[0])
    assert sent["chat_template_kwargs"] == {"reasoning_strength": "low"}
    assert "reasoning_effort" not in sent
    assert sent["messages"][2]["content"][-1] == {"type": "text", "text": ANSWER_SHAPE}
    assert seen[0].headers["authorization"] == "Bearer test-endpoint-token"
    assert ledger.usage[0].cost_usd == 0.0  # our own GPU: no per-call price


@pytest.mark.parametrize(
    "content",
    [
        # Shapes Glimmer gave when the server did not enforce the schema (2026-10-29).
        '{"decision":"fix","confidence":0.88,"fix_target":"small orange fox","fix_parts":["vest"],'
        '"fix_instruction":"remove the blue vest","issues":{"CONT-04":"Pip wears a blue vest"}}',
        '{"decision":"fix","confidence":0.88,"fix_target":"small orange fox","fix_parts":["vest"],'
        '"fix_instruction":"remove the blue vest","reason":"CONT-04: Pip wears a blue vest"}',
    ],
)
async def test_glimmer_answers_off_schema_are_repaired(
    caller: ModelCaller, storage: LocalFileMediaStorage, content: str
) -> None:
    transport, _ = replay(answering("review_glimmer", content))
    reviewer = GlimmerReviewerAdapter(glimmer_client(transport), caller, storage, "muse-glimmer", POLICY)

    v = await reviewer.review(await review_request(storage))

    assert [(i.rule_id, i.severity, i.description) for i in v.issues] == [
        ("CONT-04", Severity.MAJOR, "Pip wears a blue vest")  # the rubric sets the severity
    ]
    assert (v.fix_target, v.fix_parts, v.fix_instruction) == ("small orange fox", ("vest",), "remove the blue vest")
    assert v.can_fix


async def test_an_answer_citing_an_unknown_rule_is_retried_once_then_refused(
    caller: ModelCaller, storage: LocalFileMediaStorage
) -> None:
    bad = (
        '{"decision":"ask","confidence":0.5,"issues":[{"rule_id":"XYZ-99","description":"x"}],'
        '"fix_target":"","fix_parts":[],"fix_instruction":""}'
    )
    transport, seen = replay(answering("review_glimmer", bad) * 2)
    reviewer = GlimmerReviewerAdapter(glimmer_client(transport), caller, storage, "muse-glimmer", POLICY)

    with pytest.raises(InvalidModelOutputError):
        await reviewer.review(await review_request(storage))

    retry = body(seen[1])["messages"][-1]["content"]
    assert "XYZ-99" in retry
    assert "not in the rubric" in retry
