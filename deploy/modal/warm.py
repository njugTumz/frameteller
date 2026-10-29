"""Warm the Muse Glimmer endpoint before a demo, and say how long the cold start took (docs/runbook.md).

    python3 deploy/modal/warm.py                 # wake it: poll /health until vLLM answers
    python3 deploy/modal/warm.py --check         # and send one tiny authenticated chat request
    python3 deploy/modal/warm.py --keep 120      # keep it warm for 2 hours and lease it to production

The first request starts the GPU container (scale to zero after 5 idle minutes). /health needs no token. --check
reads the endpoint token from GLIMMER_API_KEY or ~/.config/frameteller/glimmer.token and never prints it.

The backend uses Glimmer only while it holds a lease from this script, so visitors never wake the GPU. --keep
sends a tiny request every 4 minutes (the GPU stays up) and renews a 10-minute lease on each --api after it
answers. Ctrl-C, or the end of --keep, revokes the leases: reviews go back to Spark at once, and the GPU scales to
zero 5 minutes later. If this script dies, the lease runs out by itself within 10 minutes.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

URL = os.environ.get("GLIMMER_URL", "https://geoftums--frameteller-glimmer-serve.us-east.modal.run")
TOKEN_FILE = pathlib.Path.home() / ".config" / "frameteller" / "glimmer.token"
APIS = {
    "production": "https://api.frameteller.com",
    "staging": "https://ca-frameteller-staging.orangeplant-e171b35e.eastus2.azurecontainerapps.io",
}
PING_S = 240  # under Modal's 5-minute scale-down window
LEASE_MIN = 10


def token() -> str:
    return os.environ.get("GLIMMER_API_KEY") or TOKEN_FILE.read_text().strip()


def health(base: str) -> int:
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError):
        return 0


def check(base: str) -> None:
    body = {
        "model": "muse-glimmer",
        "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
        "max_tokens": 512,
        "chat_template_kwargs": {"reasoning_strength": "low"},
    }
    request = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token()}"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=120) as r:
        answer = json.load(r)["choices"][0]["message"]["content"]
    print(f"chat: {answer.strip()[:40]!r} in {time.monotonic() - started:.1f} s")


def lease(api: str, minutes: int | None) -> str:
    """Grant (minutes) or revoke (None) the backend's Glimmer lease. Returns when it now runs out."""
    method, body = ("POST", json.dumps({"minutes": minutes}).encode()) if minutes else ("DELETE", None)
    request = urllib.request.Request(
        f"{api}/internal/glimmer/lease",
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token()}"},
    )
    with urllib.request.urlopen(request, timeout=30) as r:
        return str(json.load(r)["warm_until"])


def keep(base: str, apis: list[str], minutes: float) -> None:
    end = time.monotonic() + 60 * minutes
    try:
        while time.monotonic() < end:
            check(base)  # keeps the container busy, and proves it answers before leasing it
            for api in apis:
                try:
                    print(f"  lease {api}: warm until {lease(api, LEASE_MIN)}", flush=True)
                except (urllib.error.URLError, TimeoutError) as e:
                    print(f"  lease {api} failed: {e}", flush=True)
            time.sleep(min(PING_S, max(0, end - time.monotonic())))
    except KeyboardInterrupt:
        pass
    finally:
        for api in apis:
            try:
                lease(api, None)
                print(f"lease {api} revoked: reviews use Spark; Glimmer scales to zero in 5 minutes")
            except (urllib.error.URLError, TimeoutError) as e:
                print(f"revoking {api} failed ({e}); it runs out within {LEASE_MIN} minutes anyway")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="also send one authenticated chat request")
    parser.add_argument("--timeout", type=float, default=900, help="give up after this many seconds")
    parser.add_argument("--keep", type=float, metavar="MINUTES", help="keep it warm and leased for this long")
    parser.add_argument(
        "--api",
        action="append",
        help="backend to lease Glimmer to: production, staging or a URL (repeatable; default production)",
    )
    args = parser.parse_args()
    started = time.monotonic()
    while (status := health(URL)) != 200:
        waited = time.monotonic() - started
        if waited > args.timeout:
            raise SystemExit(f"not ready after {waited:.0f} s (last status {status})")
        print(f"{waited:6.0f} s  waiting (status {status or 'no answer'})", flush=True)
        time.sleep(10)
    print(f"ready after {time.monotonic() - started:.0f} s")
    if args.keep:
        apis = [APIS.get(a, a).rstrip("/") for a in (args.api or ["production"])]
        keep(URL, apis, args.keep)
    elif args.check:
        check(URL)


if __name__ == "__main__":
    main()
