"""Serve marketing/ locally with the headers Azure Static Web Apps adds (CSP included), for the Playwright suite.

    python3 frontend/e2e-marketing/serve.py [port]
"""

import http.server
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "marketing"
HEADERS = json.loads((ROOT / "staticwebapp.config.json").read_text())["globalHeaders"]


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        for name, value in HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def log_message(self, *args):
        pass


port = int(sys.argv[1]) if len(sys.argv) > 1 else 4174
http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
