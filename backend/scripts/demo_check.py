"""Demo-day check: wake the backend, ping every model we use, and show today's caps and what is left.

    cd backend && .venv/bin/python scripts/demo_check.py                       # production, about USD 0.003
    cd backend && .venv/bin/python scripts/demo_check.py --api staging --image # and draw one image (USD 0.01)
    cd backend && .venv/bin/python scripts/demo_check.py --glimmer             # and wake Muse Glimmer (Modal)

1. The backend: /healthz until it answers (it scales to zero), /readyz, and /status (paused or full).
2. With an admin token (ADMIN_TOKEN, or ~/.config/frameteller/admin-<api>.token): GET /admin/overview, so the
   public and judge budgets for today, every queue and the live sessions.
3. The models, straight from this machine with the local key (MODEL_API_KEY via the settings, from .env, never
   printed): Muse Spark (one tiny translation), SAM 3.1 (one click on a fixture panel), Voice Transcribe (one
   second of silence over the realtime socket), and with --image one Muse Image draft. Azure Text-to-Speech:
   the voice list (free), with AZURE_SPEECH_KEY or ~/.config/frameteller/speech.key.
4. With --glimmer: deploy/modal/warm.py --check (wakes the GPU; it scales down 5 minutes after the last request).

Prints one line per check and exits 1 if any failed. Never prints a key or token.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path.home() / ".config" / "frameteller"
APIS = {
    "production": "https://api.frameteller.com",
    "staging": "https://ca-frameteller-staging.orangeplant-e171b35e.eastus2.azurecontainerapps.io",
}
results: list[bool] = []


def report(ok: bool, name: str, detail: str) -> None:
    results.append(ok)
    print(f"{'ok  ' if ok else 'FAIL'} {name:<22} {detail}", flush=True)


def get(base: str, path: str, token: str = "", timeout: float = 30) -> tuple[int, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, headers=headers), timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, str(getattr(e, "reason", e))


def secret(env: str, file: Path) -> str:
    """From the environment or a local file; never printed."""
    value = os.environ.get(env, "")
    if not value and file.exists():
        value = file.read_text().strip()
    return value


def backend(base: str, name: str) -> None:
    started, status = time.perf_counter(), 0
    while time.perf_counter() - started < 180:
        status, _ = get(base, "/healthz", timeout=20)
        if status == 200:
            break
        time.sleep(3)
    report(status == 200, "backend up", f"{base} in {time.perf_counter() - started:.1f} s")
    status, ready = get(base, "/readyz")
    report(status == 200, "backend ready", json.dumps(ready) if status != 200 else "storage reachable")
    status, s = get(base, "/status")
    if status == 200:
        detail = f"paused={s['paused']} full={s['full']} (the overview below has the budgets)"
        report(not s["paused"] and not s["full"], "studio status", detail)
    else:
        report(False, "studio status", f"HTTP {status}")

    token = secret("ADMIN_TOKEN", CONFIG / f"admin-{name}.token")
    if not token:
        print(f"     {'admin overview':<22} skipped: no ADMIN_TOKEN or {CONFIG / f'admin-{name}.token'}")
        return
    status, o = get(base, "/admin/overview", token)
    if status != 200:
        report(False, "admin overview", f"HTTP {status}")
        return
    for b in o["budgets"]:
        money = f"${b['spent_usd']:.2f} spent, ${b['left_usd']:.2f} left of ${b['cap_usd']:.2f}"
        print(f"     budget {b['lane']:<15} {b['day']}: {money}")
    busy = ", ".join(f"{g['name']} {g['in_flight']}/{g['limit']} (+{g['waiting']} waiting)" for g in o["gates"])
    print(f"     queues                 {busy}")
    warm = o["glimmer_warm_until"] or "cold (Spark reviews)"
    print(f"     live sessions {o['live_sessions']}; Read it to me {'on' if o['read_it_to_me'] else 'OFF'}; ", end="")
    print(f"judge pass {'on' if o['judge_pass'] else 'OFF'}; Glimmer {warm}")
    report(o["read_it_to_me"] and o["judge_pass"], "admin overview", "Read it to me and judge pass are on")


async def timed(name: str, check: Callable[[], Awaitable[str]]) -> None:
    started = time.perf_counter()
    try:
        detail = await check()
        report(True, name, f"{detail} ({time.perf_counter() - started:.1f} s)")
    except Exception as e:  # report every failure and go on
        report(False, name, f"{type(e).__name__}: {getattr(e, 'user_message', '') or str(e)[:160]}")


async def models(draw: bool) -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    import httpx2

    from frameteller.application.ports import ImageRequest, SpeechOptions
    from frameteller.domain import Point
    from frameteller.infrastructure.azure.speech import AzureSpeechSynthesizer
    from frameteller.infrastructure.config import load_settings
    from frameteller.infrastructure.local import FileSpendLedger, LocalFileMediaStorage
    from frameteller.infrastructure.meta import meta_client
    from frameteller.infrastructure.meta.director import MetaSparkDirectorAdapter
    from frameteller.infrastructure.meta.image import MetaImageAdapter
    from frameteller.infrastructure.meta.sam import MetaSamAdapter
    from frameteller.infrastructure.meta.voice import MetaVoiceTranscribeAdapter, paced_pcm
    from frameteller.infrastructure.resilience import Breakers, ModelCaller

    with tempfile.TemporaryDirectory(prefix="frameteller-check-") as tmp:
        root = Path(tmp)
        speech_key = secret("AZURE_SPEECH_KEY", CONFIG / "speech.key")
        overrides: dict[str, Any] = {"app_env": "local", "local_storage_dir": root, "director_model": "muse-spark-1.3"}
        if speech_key:
            overrides["azure_speech_key"] = speech_key
        settings = load_settings(**overrides)  # the Meta key from the environment or .env, via the settings
        caller = ModelCaller(FileSpendLedger(root), Breakers())
        client = meta_client(settings)
        storage = LocalFileMediaStorage(root)

        async def spark() -> str:
            director = MetaSparkDirectorAdapter(client, caller, settings)
            [out] = await director.translate(["The kite drifts over the rooftops."], "fr-FR")
            return f"muse-spark-1.3 translated: {out[:40]!r}"

        async def sam() -> str:
            panel_bytes = (ROOT / "backend" / "tests" / "fixtures" / "images" / "panel_small.webp").read_bytes()
            panel = await storage.put("panels/check.webp", panel_bytes, "image/webp")
            segment = await MetaSamAdapter(client, caller, storage, settings).segment_point(
                panel, Point(193, 129), "masks/check"
            )
            return f"sam-3.1 {'selected an object' if segment else 'answered (no object at the point)'}"

        async def voice() -> str:
            adapter = MetaVoiceTranscribeAdapter(caller, settings)
            events = [e async for e in adapter.stream(paced_pcm(bytes(48_000)), SpeechOptions())]
            return f"muse-voice-transcribe-1.0 streamed 1 s ({len(events)} events)"

        async def image() -> str:
            request = ImageRequest(
                "Storyboard panel, pencil rough, no text. A paper kite over rooftops.", "low", "panel"
            )
            out = await MetaImageAdapter(client, caller, storage, settings).generate(request, "panels/check")
            return f"muse-image-1.0 drew {out.size.width}x{out.size.height}"

        async def tts() -> str:
            if settings.azure_speech_key is None:
                raise RuntimeError("no AZURE_SPEECH_KEY or ~/.config/frameteller/speech.key")
            async with httpx2.AsyncClient() as http:
                voices = await AzureSpeechSynthesizer(http, caller, storage, settings).voices()
            return f"{len(voices)} voices, Ava {'listed' if any('Ava' in v.name for v in voices) else 'MISSING'}"

        await timed("Muse Spark", spark)
        await timed("SAM 3.1", sam)
        await timed("Voice Transcribe", voice)
        if draw:
            await timed("Muse Image", image)
        else:
            print(f"     {'Muse Image':<22} skipped: --image draws one draft (USD 0.01)")
        await timed("Azure Text-to-Speech", tts)
        rows = (
            [json.loads(line) for line in (root / "spend.jsonl").read_text().splitlines()]
            if (root / "spend.jsonl").exists()
            else []
        )
        print(f"     spent by this check    ${sum(r.get('cost_usd', 0) for r in rows if r.get('type') == 'usage'):.4f}")


def glimmer() -> None:
    started = time.perf_counter()
    done = subprocess.run([sys.executable, str(ROOT / "deploy" / "modal" / "warm.py"), "--check"], check=False)
    report(done.returncode == 0, "Muse Glimmer", f"warm.py --check in {time.perf_counter() - started:.0f} s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--api", default="production", help="production, staging, or a URL")
    parser.add_argument("--image", action="store_true", help="also draw one Muse Image draft (USD 0.01)")
    parser.add_argument("--glimmer", action="store_true", help="also wake Muse Glimmer on Modal")
    parser.add_argument("--no-models", action="store_true", help="only the backend checks")
    args = parser.parse_args()
    base = APIS.get(args.api, args.api).rstrip("/")
    name = args.api if args.api in APIS else "custom"
    backend(base, name)
    if not args.no_models:
        asyncio.run(models(args.image))
    if args.glimmer:
        glimmer()
    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
