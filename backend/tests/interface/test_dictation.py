import io
import wave

from frameteller.domain import TranscriptTurn
from tests.interface.conftest import Api


def wav(seconds: float, rate: int = 24_000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


async def test_dictation_returns_the_text_to_review(api: Api) -> None:
    api.fakes.speech.turns = [TranscriptTurn("0", "make her raincoat red", 0, 1500)]
    r = await api.client.post("/projects/p1/dictation", content=wav(2), headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200
    assert r.json() == {"text": "make her raincoat red"}


async def test_dictation_takes_up_to_30_seconds_past_the_usual_body_limit(api: Api) -> None:
    r = await api.client.post("/projects/p1/dictation", content=wav(29.9), headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200
    r = await api.client.post("/projects/p1/dictation", content=wav(31), headers={"Content-Type": "audio/wav"})
    assert r.status_code == 413


async def test_dictation_needs_a_wav(api: Api) -> None:
    r = await api.client.post(
        "/projects/p1/dictation", content=b"not audio" * 10, headers={"Content-Type": "audio/wav"}
    )
    assert r.status_code == 422
    assert "WAV" in r.json()["error"]["message"]


async def test_dictation_for_an_unknown_project_is_404(api: Api) -> None:
    r = await api.client.post("/projects/nope/dictation", content=wav(1), headers={"Content-Type": "audio/wav"})
    assert r.status_code == 404
