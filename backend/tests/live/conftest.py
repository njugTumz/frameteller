"""Live tests: real Meta calls with real credits. Skipped unless RUN_LIVE=1; the whole run is capped at $0.30.

    cd backend && RUN_LIVE=1 .venv/bin/pytest -m live -s

MODEL_API_KEY comes from .env through the settings class. The director runs on the contributor model locally,
so only the synthetic test story is sent.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from frameteller.infrastructure.config import Settings, load_settings
from frameteller.infrastructure.resilience import Breakers, ModelCaller
from tests.fakes import InMemorySpendLedger

BUDGET_USD = 0.30
LEDGER = InMemorySpendLedger()


def spent() -> float:
    return sum(u.cost_usd for u in LEDGER.usage)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    skip = pytest.mark.skip(reason="live test: set RUN_LIVE=1 to spend real credits")
    for item in items:
        if "tests/live/" in item.nodeid:
            item.add_marker(pytest.mark.live)
            if os.environ.get("RUN_LIVE") != "1":
                item.add_marker(skip)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    if not LEDGER.usage:
        return
    terminalreporter.section("live spend")
    for u in LEDGER.usage:
        terminalreporter.write_line(
            f"{u.model:28} {u.operation:16} {u.latency_ms:>6} ms  ${u.cost_usd:.4f}  "
            f"in={u.input_tokens} out={u.output_tokens} cached={u.cached_tokens} ok={u.ok}"
        )
    terminalreporter.write_line(f"total ${spent():.4f} of ${BUDGET_USD:.2f}")


@pytest.fixture
def reserve() -> Callable[[float], None]:
    def check(cost_usd: float) -> None:
        if spent() + cost_usd > BUDGET_USD:
            pytest.fail(f"live budget ${BUDGET_USD} would be exceeded")

    return check


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return load_settings(app_env="local", local_storage_dir=tmp_path)


@pytest.fixture
def caller() -> ModelCaller:
    return ModelCaller(LEDGER, Breakers())
