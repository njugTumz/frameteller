"""Warm the Muse Glimmer endpoint before a demo, and say how long the cold start took (docs/runbook.md).

    python3 deploy/modal/warm.py                 # wake it: poll /health until vLLM answers
    python3 deploy/modal/warm.py --check         # and send one tiny authenticated chat request

The first request starts the GPU container (scale to zero after 5 idle minutes). /health needs no token. --check
reads the endpoint token from GLIMMER_API_KEY or ~/.config/frameteller/glimmer.token and never prints it.
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


def health(base: str) -> int:
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError):
        return 0


def check(base: str) -> None:
    token = os.environ.get("GLIMMER_API_KEY") or TOKEN_FILE.read_text().strip()
    body = {
        "model": "muse-glimmer",
        "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
        "max_tokens": 512,
        "chat_template_kwargs": {"reasoning_strength": "low"},
    }
    request = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=120) as r:
        answer = json.load(r)["choices"][0]["message"]["content"]
    print(f"chat: {answer.strip()[:40]!r} in {time.monotonic() - started:.1f} s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="also send one authenticated chat request")
    parser.add_argument("--timeout", type=float, default=900, help="give up after this many seconds")
    args = parser.parse_args()
    started = time.monotonic()
    while (status := health(URL)) != 200:
        waited = time.monotonic() - started
        if waited > args.timeout:
            raise SystemExit(f"not ready after {waited:.0f} s (last status {status})")
        print(f"{waited:6.0f} s  waiting (status {status or 'no answer'})", flush=True)
        time.sleep(10)
    print(f"ready after {time.monotonic() - started:.0f} s")
    if args.check:
        check(URL)


if __name__ == "__main__":
    main()
