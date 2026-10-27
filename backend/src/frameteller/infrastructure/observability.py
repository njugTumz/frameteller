"""Structured JSON logs with request and project IDs. Secrets, audio and base64 images never reach a log."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
project_id_var: ContextVar[str | None] = ContextVar("project_id", default=None)

_KEY = re.compile(r"\bLLM_[A-Za-z0-9_\-]{8,}")
_BEARER = re.compile(r"(?i)\bbearer\s+\S+")
_DATA_URL = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+")
_BASE64_RUN = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")
_STANDARD = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def redact(text: str) -> str:
    text = _KEY.sub("[redacted key]", text)
    text = _BEARER.sub("Bearer [redacted]", text)
    text = _DATA_URL.sub(lambda m: f"[redacted data url, {len(m.group(0))} chars]", text)
    return _BASE64_RUN.sub(lambda m: f"[redacted base64, {len(m.group(0))} chars]", text)


def _clean(value: Any) -> Any:
    if isinstance(value, bytes | bytearray | memoryview):
        return f"[{len(value)} bytes]"  # raw audio or images never get logged
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
            "request_id": request_id_var.get(),
            "project_id": project_id_var.get(),
        }
        line.update({k: _clean(v) for k, v in vars(record).items() if k not in _STANDARD})
        if record.exc_info:
            line["error"] = redact(self.formatException(record.exc_info))
        return json.dumps(line, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpx2", "httpcore", "openai", "websockets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # their debug logs can include request bodies


@contextmanager
def log_context(*, request_id: str | None = None, project_id: str | None = None) -> Iterator[None]:
    tokens = []
    if request_id is not None:
        tokens.append((request_id_var, request_id_var.set(request_id)))
    if project_id is not None:
        tokens.append((project_id_var, project_id_var.set(project_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
