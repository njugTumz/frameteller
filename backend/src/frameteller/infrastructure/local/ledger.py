from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any

from frameteller.application.ports import UsageRecord


class FileSpendLedger:
    """SpendLedger as an append-only JSONL file. Charges count toward budgets; usage lines are metrics only."""

    def __init__(self, root: Path) -> None:
        self._path = root / "spend.jsonl"
        self._lock = asyncio.Lock()

    async def spent_by_project(self, project_id: str) -> float:
        return sum(float(r["cost_usd"]) for r in await self._charges() if r["project_id"] == project_id)

    async def spent_on_day(self, day: str) -> float:
        return sum(float(r["cost_usd"]) for r in await self._charges() if r["day"] == day)

    async def record(self, project_id: str, day: str, cost_usd: float, what: str) -> None:
        await self._append({"type": "charge", "project_id": project_id, "day": day, "cost_usd": cost_usd, "what": what})

    async def record_usage(self, usage: UsageRecord) -> None:
        await self._append({"type": "usage", **dataclasses.asdict(usage)})

    async def usage(self) -> list[UsageRecord]:
        return [
            UsageRecord(**{k: v for k, v in r.items() if k != "type"})
            for r in await self._read()
            if r["type"] == "usage"
        ]

    async def _charges(self) -> list[dict[str, Any]]:
        return [r for r in await self._read() if r["type"] == "charge"]

    async def _read(self) -> list[dict[str, Any]]:
        def read() -> list[dict[str, Any]]:
            if not self._path.exists():
                return []
            return [json.loads(line) for line in self._path.read_text("utf-8").splitlines() if line.strip()]

        return await asyncio.to_thread(read)

    async def _append(self, row: dict[str, Any]) -> None:
        def append() -> None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")

        async with self._lock:
            await asyncio.to_thread(append)
