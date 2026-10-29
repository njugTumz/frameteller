"""ReviewerPort on any OpenAI-compatible Chat Completions endpoint with images and a strict JSON schema (ADR 0012).

SparkReviewerAdapter calls Meta's Model API (muse-spark-1.3; the contributor model only in local dev).
GlimmerReviewerAdapter calls our own vLLM endpoint for Muse Glimmer on Modal (ADR 0013). Same prompt, same
schema: the eval compares the models, not the prompts.

The rubric's severities are authoritative: the model names the rule, the rubric says how serious it is.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import time
from collections.abc import Sequence
from typing import Any, Literal

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from PIL import Image
from pydantic import BaseModel, Field, ValidationError

from frameteller.application.errors import InvalidModelOutputError
from frameteller.application.ports import MediaStoragePort, ReviewRequest
from frameteller.application.rubrics import RubricSet
from frameteller.domain import Decision, Issue, MediaRef, Verdict
from frameteller.infrastructure.pricing import token_cost
from frameteller.infrastructure.resilience import ModelCaller, RetryPolicy, Usage

IMAGE_SIDE = 768  # long side sent to the reviewer: enough to judge clothing and colours, a fraction of the tokens
MAX_OUTPUT_TOKENS = 4096  # Glimmer reasons before it answers; a tight budget cuts the answer off

# Stable prefix part 1: identical bytes on every request, so prompt caching can hit.
REVIEW_PROMPT = """You are the continuity supervisor of Frameteller, a tool that turns spoken stories into storyboards.
You check one image against a rubric and answer in JSON.
You receive the rubric (guidance, then rules with an id, a severity and a one-line test), the project style and
the images: character reference sheets first, each labelled with the character's name and description, then the
image under review. For a panel you also get its shot: framing, the characters it lists, setting and action.

Check every rule. Report an issue only for a rule the image clearly breaks: cite the rule id and say in one
short sentence what is wrong and where, naming the character (e.g. "Pip wears a blue vest that is not on his
reference sheet"). Never report what you cannot see, and never invent rules.

decision:
- pass: no rule with severity blocker or major is broken.
- fix: a blocker or major issue that ONE appearance edit of ONE object can repair: added, missing or wrongly
  coloured clothing or accessories, wrong hair, fur or skin colour, or an extra character or object that can
  simply be removed. Then fix_target names that object as it looks in the picture (e.g. "small orange fox"),
  fix_parts lists every part the change must reach (e.g. ["vest"]), and fix_instruction is the change as a
  short imperative (e.g. "remove the blue vest, the fox wears nothing").
- ask: a blocker or major issue an appearance edit cannot repair (a missing character, the wrong species, the
  wrong framing or action, the whole image in another style), several unrelated issues, or you are unsure.
confidence: how sure you are of your decision, from 0 to 1.
fix_target, fix_parts and fix_instruction are "" and [] unless decision is fix."""


class _IssueOut(BaseModel):
    rule_id: str
    description: str = Field(min_length=1, max_length=400)


class _VerdictOut(BaseModel):
    decision: Literal["pass", "fix", "ask"]
    confidence: float
    # Glimmer on vLLM does not enforce the schema and may leave out an empty array: none listed means none found.
    issues: list[_IssueOut] = Field(default_factory=list, max_length=12)
    fix_target: str = Field(max_length=120)
    fix_parts: list[str] = Field(max_length=8)
    fix_instruction: str = Field(max_length=300)


def verdict_schema(rule_ids: Sequence[str]) -> dict[str, Any]:
    """Strict JSON schema: rule ids are an enum of the rubric's own, so the model cannot cite a rule that isn't."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["decision", "confidence", "issues", "fix_target", "fix_parts", "fix_instruction"],
        "properties": {
            "decision": {"type": "string", "enum": ["pass", "fix", "ask"]},
            "confidence": {"type": "number"},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["rule_id", "description"],
                    "properties": {
                        "rule_id": {"type": "string", "enum": list(rule_ids)},
                        "description": {"type": "string"},
                    },
                },
            },
            "fix_target": {"type": "string"},
            "fix_parts": {"type": "array", "items": {"type": "string"}},
            "fix_instruction": {"type": "string"},
        },
    }


def rubric_message(rubrics: RubricSet) -> str:
    """Stable prefix part 2: the rubric text, the same for every review of the same step."""
    blocks = []
    for r in rubrics.rubrics:
        rules = "\n".join(f"- {rule.id} ({rule.severity.value}): {rule.test}" for rule in r.rules)
        blocks.append(f"## Rubric {r.id} (version {r.version})\n{r.guidance}\n\nRules:\n{rules}")
    return "\n\n".join(blocks)


def data_url(data: bytes, side: int = IMAGE_SIDE) -> str:
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGB")
    image.thumbnail((side, side))
    out = io.BytesIO()
    image.save(out, "WEBP", quality=82)
    return "data:image/webp;base64," + base64.b64encode(out.getvalue()).decode()


class ChatReviewer:
    """The shared implementation. Subclasses pick the client, the model and how reasoning is set."""

    def __init__(
        self,
        client: AsyncOpenAI,
        caller: ModelCaller,
        storage: MediaStoragePort,
        model: str,
        policy: RetryPolicy,
        *,
        priced: bool,
    ) -> None:
        self._client, self._caller, self._storage = client, caller, storage
        self._model, self._policy, self._priced = model, policy, priced

    @property
    def model(self) -> str:
        return self._model

    def _request_options(self) -> dict[str, Any]:
        return {}

    async def review(self, request: ReviewRequest) -> Verdict:
        started = time.perf_counter()
        messages = await self._messages(request)
        rule_ids = [r.id for r in request.rubric.rules]
        schema = verdict_schema(rule_ids)
        for attempt in (1, 2):

            async def call(msgs: list[dict[str, Any]] = messages) -> tuple[str, Usage]:
                params: dict[str, Any] = {
                    "model": self._model,
                    "messages": msgs,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": "continuity_verdict", "strict": True, "schema": schema},
                    },
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    **self._request_options(),
                }
                completion: ChatCompletion = await self._client.chat.completions.create(**params)
                u = completion.usage
                cached = u.prompt_tokens_details.cached_tokens if u and u.prompt_tokens_details else None
                tokens_in, tokens_out = (u.prompt_tokens, u.completion_tokens) if u else (None, None)
                cost = token_cost(self._model, tokens_in, tokens_out, cached) if self._priced else 0.0
                return completion.choices[0].message.content or "", Usage(cost, tokens_in, tokens_out, cached)

            raw = await self._caller.call(self._model, "review", call, self._policy)
            out, problem = _parse(raw, rule_ids)
            if out is not None:
                return self._verdict(out, request.rubric, started)
            if attempt == 2:
                raise InvalidModelOutputError(self._model, problem)
            messages = [
                *messages,
                {"role": "assistant", "content": raw or "(empty)"},
                {"role": "user", "content": f"That answer failed validation: {problem}. Return a corrected answer."},
            ]
        raise AssertionError("unreachable")  # pragma: no cover

    async def _messages(self, request: ReviewRequest) -> list[dict[str, Any]]:
        sheets = await asyncio.gather(*(self._image(s.image) for s in request.reference_sheets))
        reviewed = await asyncio.gather(*(self._image(i) for i in request.images))
        context: dict[str, Any] = {"project_style": request.style.value}
        if request.shot is not None:
            s = request.shot
            names = [sh.name for sh in request.reference_sheets]
            context["shot"] = {
                "number": s.number,
                "framing": s.framing.value,
                "characters": names or list(s.character_ids),
                "setting": s.setting,
                "action": s.action,
            }
        if request.subject:
            context["subject"] = request.subject
        if request.previous_issues:
            context["issues_a_fix_tried_to_repair"] = [f"{i.rule_id}: {i.description}" for i in request.previous_issues]
        content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(context, ensure_ascii=False)}]
        for sheet, url in zip(request.reference_sheets, sheets, strict=True):
            content.append({"type": "text", "text": f"Reference sheet: {sheet.name}: {sheet.description}"})
            content.append({"type": "image_url", "image_url": {"url": url}})
        content.append({"type": "text", "text": "Image under review:"})
        content.extend({"type": "image_url", "image_url": {"url": url}} for url in reviewed)
        return [
            {"role": "system", "content": REVIEW_PROMPT},
            {"role": "system", "content": rubric_message(request.rubric)},
            {"role": "user", "content": content},
        ]

    async def _image(self, ref: MediaRef) -> str:
        data = await self._storage.get(ref)
        return await asyncio.to_thread(data_url, data)

    def _verdict(self, out: _VerdictOut, rubrics: RubricSet, started: float) -> Verdict:
        issues: list[Issue] = []
        for i in out.issues:
            rule = rubrics.rule(i.rule_id)
            if rule is not None and all(x.rule_id != rule.id or x.description != i.description for x in issues):
                issues.append(Issue(rule.id, rule.severity, i.description.strip()))
        fixing = out.decision == "fix"
        return Verdict(
            decision=Decision(out.decision),
            confidence=min(1.0, max(0.0, out.confidence)),
            issues=tuple(issues),
            fix_instruction=out.fix_instruction.strip() if fixing else "",
            fix_target=out.fix_target.strip() if fixing else "",
            fix_parts=tuple(p.strip() for p in out.fix_parts if p.strip()) if fixing else (),
            model=self._model,
            latency_ms=round((time.perf_counter() - started) * 1000),
            rubrics=tuple(rubrics.hashes.items()),
        )


# Example answer for models whose server does not enforce the schema (Glimmer on vLLM, ADR 0013).
ANSWER_SHAPE = (
    'Answer with one JSON object of exactly this shape, and nothing else: {"decision": "fix", "confidence": 0.9, '
    '"issues": [{"rule_id": "CONT-04", "description": "Pip wears a blue vest that is not on his reference sheet"}], '
    '"fix_target": "small orange fox", "fix_parts": ["vest"], "fix_instruction": "remove the blue vest"}. '
    'List every broken rule in "issues" (an array, [] when none); never put issues anywhere else.'
)
_CITED = re.compile(r"\b([A-Z]+-\d{2})\b\s*[:\-\u2013]\s*(.+)")


def _normalise(data: Any) -> Any:
    """Repair the shapes a schema-less answer takes: issues as {rule_id: description}, or issues left out and
    a rule cited in a stray field ("reason": "CONT-04: ..."). Anything else is left for validation to refuse."""
    if not isinstance(data, dict):
        return data
    issues = data.get("issues")
    if isinstance(issues, dict):
        data["issues"] = [{"rule_id": k, "description": str(v)} for k, v in issues.items()]
    elif issues is None:
        cited = []
        for key, value in data.items():
            if key not in _VerdictOut.model_fields and isinstance(value, str):
                cited += [{"rule_id": m[1], "description": m[2].strip()} for m in _CITED.finditer(value)]
        data["issues"] = cited
    return data


def _parse(raw: str, rule_ids: Sequence[str]) -> tuple[_VerdictOut | None, str]:
    text = raw.strip()
    if text.startswith("```"):  # tolerate a fenced answer
        text = text.strip("`").removeprefix("json").strip()
    try:
        out = _VerdictOut.model_validate(_normalise(json.loads(text)))
    except json.JSONDecodeError as e:
        return None, f"not JSON: {e.msg}"
    except ValidationError as e:
        return None, "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:5])
    unknown = sorted({i.rule_id for i in out.issues} - set(rule_ids))
    if unknown:
        return None, f"issues cite rules {unknown} that are not in the rubric"
    return out, ""


class SparkReviewerAdapter(ChatReviewer):
    """Muse Spark on Meta's Model API, with images and low reasoning effort."""

    def __init__(
        self,
        client: AsyncOpenAI,
        caller: ModelCaller,
        storage: MediaStoragePort,
        model: str,
        policy: RetryPolicy,
        effort: str = "low",
    ) -> None:
        super().__init__(client, caller, storage, model, policy, priced=True)
        self._effort = effort

    def _request_options(self) -> dict[str, Any]:
        return {"reasoning_effort": self._effort}


class GlimmerReviewerAdapter(ChatReviewer):
    """Muse Glimmer on our Modal vLLM endpoint. Reasoning strength is a chat-template argument there, and the
    model's own sampling (temperature 1.0, top_p 0.95, top_k 64) comes from the server's generation config."""

    def __init__(
        self,
        client: AsyncOpenAI,
        caller: ModelCaller,
        storage: MediaStoragePort,
        model: str,
        policy: RetryPolicy,
        strength: str = "low",
    ) -> None:
        super().__init__(client, caller, storage, model, policy, priced=False)
        self._strength = strength

    def _request_options(self) -> dict[str, Any]:
        return {"extra_body": {"chat_template_kwargs": {"reasoning_strength": self._strength}}}

    async def _messages(self, request: ReviewRequest) -> list[dict[str, Any]]:
        """The same prompt plus the answer's shape spelled out: the server accepts the schema but does not
        enforce it (it answered with extra keys and issues as an object), so the model has to know the shape."""
        messages = await super()._messages(request)
        messages[-1]["content"].append({"type": "text", "text": ANSWER_SHAPE})
        return messages
