import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from frameteller.application.budget import LimitBudgetGuard
from frameteller.application.errors import BudgetExceededError, ProjectNotFoundError
from frameteller.application.ports import UsageRecord
from frameteller.domain import (
    AnimaticExport,
    CanvasTransform,
    CleanPlate,
    MediaRef,
    ObjectMask,
    PanelStyle,
    Project,
    SheetRefusal,
    Size,
)
from frameteller.infrastructure.local import (
    FileSpendLedger,
    FileVisitorQuota,
    JsonFileProjectRepository,
    LocalFileMediaStorage,
)
from tests.builders import bitmap, costume_project, project
from tests.fakes import FixedClock


async def test_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalFileMediaStorage(tmp_path)
    ref = await storage.put("projects/p1/panels/s1/r1", b"webp-bytes", "image/webp")
    assert ref == MediaRef("projects/p1/panels/s1/r1")
    assert await storage.get(ref) == b"webp-bytes"


@pytest.mark.parametrize("key", ["../escape", "/etc/passwd", "a/../../b", "", " space"])
async def test_storage_refuses_unsafe_keys(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError, match="unsafe"):
        await LocalFileMediaStorage(tmp_path).put(key, b"x", "text/plain")


async def test_repository_round_trips_a_full_project(tmp_path: Path) -> None:
    p = project(shots=3)
    p.style = PanelStyle.PAPER_CUTOUT
    panel = p.panel("s2")
    panel.record_render(1, MediaRef("panels/s2/r1"), "resp_1", Size(1920, 1280))
    panel.cache_mask(1, ObjectMask("character:mira", "Mira", bitmap(10, 20, 110, 220), MediaRef("m/mira.png"), "mira"))
    panel.transform(CanvasTransform("character:mira", dx=4, dy=-2, scale=1.1))
    panel.cache_plate(1, CleanPlate(("character:mira",), MediaRef("panels/s2/r1/plates/a"), "resp_2"))
    panel.record_composite(1, MediaRef("panels/s2/r1/composites/b.webp"), Size(1920, 1280))
    p.reorder_shots(["s3", "s1", "s2"])
    p.record_animatic(AnimaticExport(MediaRef("projects/p1/exports/animatic-x.mp4"), 12000, True, False))
    p.share("tok", public=True)

    repo = JsonFileProjectRepository(tmp_path)
    await repo.save(p)
    loaded = await repo.get("p1")

    assert loaded == p
    assert loaded.bible.is_approved


async def test_repository_keeps_looks_outfits_and_voice_offsets(tmp_path: Path) -> None:
    p = costume_project()
    p.change_outfit("wren", None, "s6")
    p.shots[2] = replace(p.shots[2], voice_from_ms=1200)
    p.sheet_refusals["wren"] = SheetRefusal("the description refused", "friendly storybook character")
    repo = JsonFileProjectRepository(tmp_path)
    await repo.save(p)
    loaded = await repo.get("p1")
    assert loaded.bible.get("wren").looks == p.bible.get("wren").looks
    assert loaded.outfits == p.outfits
    assert loaded.shots[2].voice_from_ms == 1200
    assert loaded.sheet_refusals == p.sheet_refusals
    assert loaded.bible.is_approved is p.bible.is_approved


async def test_repository_unknown_project(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError):
        await JsonFileProjectRepository(tmp_path).get("nope")


async def test_repository_rejects_unknown_schema(tmp_path: Path) -> None:
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "p1.json").write_text('{"schema": 99}')
    with pytest.raises(ValueError, match="schema"):
        await JsonFileProjectRepository(tmp_path).get("p1")


async def test_ledger_drives_the_budget_guard_and_survives_restarts(tmp_path: Path) -> None:
    guard = LimitBudgetGuard(FileSpendLedger(tmp_path), FixedClock(), per_project_usd=0.02, per_day_usd=1)
    await guard.charge("p1", 0.01, "panel")
    await guard.charge("p1", 0.01, "panel")
    restarted = LimitBudgetGuard(FileSpendLedger(tmp_path), FixedClock(), per_project_usd=0.02, per_day_usd=1)
    with pytest.raises(BudgetExceededError):
        await restarted.charge("p1", 0.01, "panel")
    assert await FileSpendLedger(tmp_path).spent_on_day("2026-10-28") == pytest.approx(0.02)


async def test_usage_records_do_not_count_toward_budgets(tmp_path: Path) -> None:
    ledger = FileSpendLedger(tmp_path)
    usage = UsageRecord("muse-image-1.0", "generate", 18000, 0.01, "p1", ok=True)
    await ledger.record_usage(usage)
    assert await ledger.spent_by_project("p1") == 0
    assert await ledger.usage() == [usage]


async def test_json_repository_update_is_atomic_per_project(tmp_path: Path) -> None:
    repo = JsonFileProjectRepository(tmp_path)
    await repo.save(Project(id="p1", title="0"))

    async def bump() -> None:
        def change(p: Project) -> None:
            p.title = str(int(p.title) + 1)

        await repo.update("p1", change)

    await asyncio.gather(*(bump() for _ in range(20)))
    assert (await repo.get("p1")).title == "20"


async def test_json_repository_update_saves_nothing_when_the_change_fails(tmp_path: Path) -> None:
    repo = JsonFileProjectRepository(tmp_path)
    await repo.save(Project(id="p1", title="kept"))

    def change(p: Project) -> None:
        p.title = "lost"
        raise ValueError("rule broken")

    with pytest.raises(ValueError, match="rule broken"):
        await repo.update("p1", change)
    assert (await repo.get("p1")).title == "kept"


async def test_visitor_quota_counts_per_visitor_day_and_kind(tmp_path: Path) -> None:
    quota = FileVisitorQuota(tmp_path)
    await asyncio.gather(*(quota.add("v1", "2026-11-02", "projects") for _ in range(3)))
    await quota.add("v2", "2026-11-02", "projects")

    again = FileVisitorQuota(tmp_path)  # survives a restart
    assert await again.used("v1", "2026-11-02", "projects") == 3
    assert await again.used("v1", "2026-11-03", "projects") == 0
    assert await again.used("v2", "2026-11-02", "projects") == 1
    with pytest.raises(ValueError, match="key"):
        await quota.used("../escape", "2026-11-02", "projects")
