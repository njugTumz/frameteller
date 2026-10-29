"""Rubrics: versioned markdown files of rules a reviewer checks a pipeline step against (ADR 0012).

Parsing is pure: infrastructure reads the files (agents/*.md) and hands the text to `parse_rubric`. The hash of
the exact text is kept with every verdict, so a decision can be traced to the rules that produced it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from frameteller.domain import Severity

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_RULE_ROW = re.compile(r"^\|\s*([A-Z]+-\d{2})\s*\|\s*(blocker|major|minor)\s*\|\s*(.+?)\s*\|\s*$", re.M)


class RubricError(ValueError):
    """A rubric file is malformed: a deployment error, never a user error."""


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    severity: Severity
    test: str


@dataclass(frozen=True, slots=True)
class Rubric:
    id: str
    version: int
    hash: str  # sha256 of the file text, first 12 hex digits
    guidance: str
    rules: tuple[Rule, ...]

    def rule(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rules if r.id == rule_id), None)


def parse_rubric(text: str) -> Rubric:
    front = _FRONT_MATTER.match(text)
    if not front:
        raise RubricError("a rubric starts with front matter between --- lines")
    meta = dict(line.split(":", 1) for line in front.group(1).splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    if "id" not in meta or not meta.get("version", "").isdigit():
        raise RubricError("rubric front matter needs an id and an integer version")
    body = text[front.end() :]
    rules = tuple(Rule(m[1], Severity(m[2]), m[3]) for m in _RULE_ROW.finditer(body))
    if not rules:
        raise RubricError(f"rubric {meta['id']} has no rules")
    ids = [r.id for r in rules]
    if len(set(ids)) != len(ids):
        raise RubricError(f"rubric {meta['id']} repeats a rule id")
    guidance = body.split("## Rules", 1)[0]
    guidance = "\n".join(line for line in guidance.splitlines() if not line.startswith("# ")).strip()
    digest = hashlib.sha256(text.encode()).hexdigest()[:12]
    return Rubric(meta["id"], int(meta["version"]), digest, guidance, rules)


@dataclass(frozen=True, slots=True)
class RubricSet:
    """The rubrics one review checks at once (a panel: continuity and shot), in order."""

    rubrics: tuple[Rubric, ...]

    @property
    def rules(self) -> tuple[Rule, ...]:
        return tuple(r for rubric in self.rubrics for r in rubric.rules)

    @property
    def hashes(self) -> dict[str, str]:
        return {r.id: r.hash for r in self.rubrics}

    def rule(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rules if r.id == rule_id), None)
