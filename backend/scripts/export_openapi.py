"""Write the API's OpenAPI schema to backend/openapi.json, or check it is current (CI).

    cd backend && .venv/bin/python scripts/export_openapi.py          # write
    cd backend && .venv/bin/python scripts/export_openapi.py --check  # exit 1 if out of date

Needs no settings or API key: the app describes itself without building adapters. The WebSocket events are
not in OpenAPI; they are documented in docs/api-events.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from frameteller.interface.app import create_app

OUT = Path(__file__).resolve().parents[1] / "openapi.json"


def render() -> str:
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    schema = render()
    if "--check" in argv:
        if not OUT.exists() or OUT.read_text() != schema:
            print("backend/openapi.json is out of date: run python scripts/export_openapi.py", file=sys.stderr)
            return 1
        print("backend/openapi.json is up to date")
        return 0
    OUT.write_text(schema)
    print(f"wrote {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
