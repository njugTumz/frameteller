import json
import logging

import pytest

from frameteller.infrastructure.observability import JsonFormatter, log_context, redact


def emit(msg: str, **extra: object) -> dict[str, object]:
    record = logging.makeLogRecord({"name": "t", "levelname": "INFO", "msg": msg, **extra})
    return json.loads(JsonFormatter().format(record))  # type: ignore[no-any-return]


def test_lines_are_json_with_request_and_project_ids() -> None:
    with log_context(request_id="req-1", project_id="p1"):
        line = emit("panel ready", model="muse-image-1.0", latency_ms=1234)
    assert line["msg"] == "panel ready"
    assert (line["request_id"], line["project_id"]) == ("req-1", "p1")
    assert (line["model"], line["latency_ms"]) == ("muse-image-1.0", 1234)
    assert emit("outside")["request_id"] is None


@pytest.mark.parametrize(
    "secret",
    ["LLM_abcdefghijklmnop1234", "Bearer LLM_abcdefghijklmnop1234", "authorization: bearer sk-something"],
)
def test_keys_are_redacted(secret: str) -> None:
    out = json.dumps(emit(f"handshake {secret}", detail={"auth": secret}))
    assert "abcdefghijklmnop" not in out
    assert "sk-something" not in out


def test_base64_images_and_raw_audio_are_never_logged() -> None:
    b64 = "iVBORw0KGgo" + "A" * 5000
    line = emit("got image", data_url=f"data:image/png;base64,{b64}", raw=b64, audio=b"\x00\x01" * 4000)
    text = json.dumps(line)
    assert "AAAAAAAAAA" not in text
    assert line["audio"] == "[8000 bytes]"
    assert "redacted base64" in str(line["raw"])
    assert "redacted data url" in str(line["data_url"])


def test_short_text_is_untouched() -> None:
    assert redact("make her raincoat red") == "make her raincoat red"


def test_exceptions_are_redacted() -> None:
    try:
        raise RuntimeError("failed with LLM_abcdefghijklmnop1234")
    except RuntimeError:
        import sys

        record = logging.makeLogRecord({"msg": "boom", "levelname": "ERROR", "exc_info": sys.exc_info()})
    assert "abcdefghijklmnop" not in JsonFormatter().format(record)
