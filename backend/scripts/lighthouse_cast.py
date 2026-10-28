"""Check character consistency on the lighthouse story, without audio. Spends real credits (about $0.10).

    cd backend && .venv/bin/python scripts/lighthouse_cast.py

The six paragraphs of spikes/fixtures/lighthouse.txt become six synthetic turns (one per beat). They go
through the paid director (muse-spark-1.3, never the contributor model: the story is the user's). Then the
script draws the cast's reference sheets, approves them and draws a draft panel per shot with Muse Image.
Pre-segmentation (SAM) runs after each panel, as in the studio.

It writes spikes/out/lighthouse/contact-sheet.png (reference sheets on top, then the panels with their shot
text) and story.json (the cast and shots), to check that Pip looks the same in every panel and that no
butterfly appears. Storage is local, under spikes/out/lighthouse/store. The key is read by the settings from
.env and never printed.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import time
from pathlib import Path

from PIL import Image, ImageDraw

from frameteller.application.use_cases import DirectTurn
from frameteller.domain import PanelStyle, TranscriptTurn
from frameteller.infrastructure.config import load_settings
from frameteller.infrastructure.imaging.text import INK, MUTED, PAPER, font, line_height, wrap
from frameteller.infrastructure.local import FileSpendLedger, JsonFileProjectRepository
from frameteller.infrastructure.meta import meta_client
from frameteller.infrastructure.meta.director import MetaSparkDirectorAdapter
from frameteller.infrastructure.resilience import Breakers, ModelCaller
from frameteller.infrastructure.system import RandomIds
from frameteller.interface.container import build_container

ROOT = Path(__file__).resolve().parents[2]
STORY = ROOT / "spikes" / "fixtures" / "lighthouse.txt"
OUT = ROOT / "spikes" / "out" / "lighthouse"
TURN_MS = 6000  # synthetic timing: each paragraph is spoken over six seconds
T0 = time.perf_counter()


def say(message: str) -> None:
    print(f"[{time.perf_counter() - T0:6.1f}s] {message}", flush=True)


async def main() -> None:
    os.environ.setdefault("DIRECTOR_MODEL", "muse-spark-1.3")
    settings = load_settings(storage_backend="local", local_storage_dir=OUT / "store")
    if settings.director.endswith("-contributor"):
        raise SystemExit("Use the paid director for the user's story: DIRECTOR_MODEL=muse-spark-1.3")
    c = build_container(settings)
    # The session's own step, called directly with its own adapters (the same files and the same ledger).
    ledger = FileSpendLedger(settings.local_storage_dir)
    caller = ModelCaller(ledger, Breakers(settings.breaker_failures, settings.breaker_cooldown_s))
    director = MetaSparkDirectorAdapter(meta_client(settings), caller, settings)
    direct = DirectTurn(JsonFileProjectRepository(settings.local_storage_dir), director, RandomIds())

    paragraphs = [p.strip() for p in STORY.read_text("utf-8").splitlines() if p.strip()]
    project = await c.create_project.execute("The Lighthouse", PanelStyle.PENCIL)
    pid = project.id
    say(f"project {pid}, director {settings.director}")

    for i, text in enumerate(paragraphs, start=1):
        turn = TranscriptTurn(f"lighthouse-b{i}", text, (i - 1) * TURN_MS, i * TURN_MS)
        directed = await direct.execute(pid, turn)
        shots = ", ".join(f"#{s.number} {s.framing.value} {list(s.character_ids)}" for s in directed.shots)
        new = ", ".join(f"{ch.name} ({ch.id})" for ch in directed.new_characters)
        revised = ", ".join(f"#{s.number} -> {list(s.character_ids)}" for s in directed.revised)
        say(f"turn {i}: {shots}" + (f" | new: {new}" if new else "") + (f" | revised: {revised}" if revised else ""))

    project = await c.get_project.execute(pid)
    cast_ids = list(project.bible.characters)
    say(f"cast: {[(ch.id, ch.canonical_description) for ch in project.bible.characters.values()]}")
    await c.request_cast.execute(pid, cast_ids)
    await c.jobs.join()
    review = await c.approve_cast.execute(pid)
    say(f"cast approved: {review.approved}")
    project = await c.get_project.execute(pid)
    for shot in project.shots:
        await c.request_render.execute(pid, shot.id, "low")
    await c.jobs.join()
    say("panels drawn")

    project = await c.get_project.execute(pid)
    OUT.mkdir(parents=True, exist_ok=True)
    sheet = await contact_sheet(c, project)
    (OUT / "contact-sheet.png").write_bytes(sheet)
    story = {
        "project_id": pid,
        "characters": [
            {"id": ch.id, "name": ch.name, "description": ch.canonical_description}
            for ch in project.bible.characters.values()
        ],
        "shots": [
            {"number": s.number, "framing": s.framing.value, "characters": list(s.character_ids), "action": s.action}
            for s in project.shots
        ],
    }
    (OUT / "story.json").write_text(json.dumps(story, indent=2), "utf-8")
    spent = await FileSpendLedger(OUT / "store").spent_by_project(pid)
    butterfly = any("butterfl" in json.dumps(x).lower() for x in (story["characters"], story["shots"]))
    say(f"wrote {OUT / 'contact-sheet.png'}; butterfly mentioned: {butterfly}; spent ${spent:.4f}")


async def contact_sheet(c, project) -> bytes:  # type: ignore[no-untyped-def]
    """Reference sheets in the first row, then the panels three to a row, each with its shot text."""
    cell_w, cell_h, text_h, pad = 480, 320, 96, 16
    refs = [ch for ch in project.bible.characters.values() if ch.reference]
    shots = project.shots
    rows = 1 + (len(shots) + 2) // 3
    width = 3 * cell_w + 4 * pad
    height = pad + 60 + rows * (cell_h + text_h + pad)
    sheet = Image.new("RGB", (max(width, len(refs) * (cell_h + pad) + pad), height), PAPER)
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, pad), "The Lighthouse: reference sheets and draft panels", font=font(30), fill=INK)
    y = pad + 60
    for i, ch in enumerate(refs):
        image = Image.open(io.BytesIO(await c.storage.get(ch.reference))).convert("RGB").resize((cell_h, cell_h))
        x = pad + i * (cell_h + pad)
        sheet.paste(image, (x, y))
        draw.text((x, y + cell_h + 8), f"{ch.name} ({ch.id})", font=font(20), fill=INK)
    for i, shot in enumerate(shots):
        x = pad + (i % 3) * (cell_w + pad)
        top = y + (1 + i // 3) * (cell_h + text_h + pad)
        panel = project.panels.get(shot.id)
        if panel is not None and panel.shown_image is not None:
            image = Image.open(io.BytesIO(await c.storage.get(panel.shown_image))).convert("RGB")
            sheet.paste(image.resize((cell_w, cell_h)), (x, top))
        label = f"#{shot.number} {shot.framing.value} {', '.join(shot.character_ids)}: {shot.action}"
        for j, line in enumerate(wrap(draw, label, 16, cell_w, max_lines=4)):
            draw.text((x, top + cell_h + 6 + j * line_height(16)), line, font=font(16), fill=MUTED)
    out = io.BytesIO()
    sheet.save(out, "PNG")
    return out.getvalue()


if __name__ == "__main__":
    asyncio.run(main())
