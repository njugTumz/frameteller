"""Teleprompter and "Read it to me" over the session WebSocket, and the voices routes (ADR 0015)."""

from collections.abc import Callable

import pytest

from frameteller.application.ports import AudioProgress, PartialTranscript, TurnCompleted, TurnEnded, TurnStarted
from frameteller.domain import TranscriptTurn
from frameteller.interface.routes import session
from tests.application.test_beats import one_shot
from tests.builders import project
from tests.fakes import LISTEN, ScriptedSpeech
from tests.interface.conftest import Api, Fakes, WsClient

PATH = "/ws/projects/p1/session"
FRAME = b"\x00\x00" * 1920  # 80 ms at 24 kHz
BRANDON = "en-US-BrandonMultilingualNeural"
AVA = "en-US-AvaMultilingualNeural"
ROOFTOP = "Wide shot. Lena feeds the pigeons.\n\nA kite drifts down."


def fresh(api: Api) -> None:
    api.fakes.repo._data["p1"] = project(shots=0)
    api.fakes.director.turns = {"b1": one_shot(), "b2": one_shot()}


async def test_read_it_to_me_voices_each_paragraph_in_the_chosen_language_and_keeps_the_narration(api: Api) -> None:
    fresh(api)
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "read", "script": ROOFTOP, "voice": BRANDON, "language": "fr-FR"})

    events = await ws.until("session.ended")
    await ws.finish()

    types = [e["type"] for e in events]
    assert types[:2] == ["session.started", "script.accepted"]
    voiced = [e for e in events if e["type"] == "script.voiced"]
    assert [(v["paragraph"], v["text"], v["original"]) for v in voiced] == [
        (0, "[fr-FR] Lena feeds the pigeons.", "Lena feeds the pigeons."),
        (1, "[fr-FR] A kite drifts down.", "A kite drifts down."),
    ]
    assert voiced[0]["audio_url"].startswith("/media/projects/p1/speech/")
    audio = await api.client.get(voiced[0]["audio_url"])
    assert (audio.status_code, audio.headers["content-type"]) == (200, "audio/wav")
    turns = [e["turn"] for e in events if e["type"] == "turn.completed"]
    assert [t["text"] for t in turns] == ["[fr-FR] Lena feeds the pigeons.", "[fr-FR] A kite drifts down."]
    assert turns[0]["direction"] == "Wide shot. Lena feeds the pigeons."
    [narration] = api.project().narrations.values()
    assert (narration.voice, narration.language) == (BRANDON, "fr-FR")
    assert len(api.project().shots) == 2
    # The share page says which voice narrated it.
    token = (await api.client.post("/projects/p1/share")).json()["token"]
    assert (await api.client.get(f"/shares/{token}")).json()["narrated_by"] == "Brandon"


async def test_pause_and_continue_are_accepted_while_a_voice_reads(api: Api) -> None:
    fresh(api)
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "read", "script": ROOFTOP})  # Ava in English by default
    await ws.send_json({"type": "pause"})
    paused = await ws.until("script.paused")
    assert paused[-1]["reason"] == "user"
    await ws.send_json({"type": "continue"})
    events = await ws.until("session.ended")
    await ws.finish()

    assert "script.resumed" in [e["type"] for e in events]
    assert len([e for e in paused + events if e["type"] == "script.voiced"]) == 2
    [narration] = api.project().narrations.values()
    assert narration.voice == AVA  # the default voice


async def test_teleprompter_cuts_the_script_paragraphs_from_the_reading(api: Api) -> None:
    fresh(api)
    speech = ScriptedSpeech(
        [
            TurnStarted("0", 0),
            PartialTranscript("Lena feeds the pigeons"),
            AudioProgress(1500),
            TurnEnded("0", 1400),
            TurnCompleted(TranscriptTurn("0", "Lena feeds the pigeons", 0, 1400)),
            LISTEN,
            TurnStarted("1", 1600),
            PartialTranscript("A kite drifts down"),
            AudioProgress(3000),
            TurnEnded("1", 2900),
            TurnCompleted(TranscriptTurn("1", "A kite drifts down", 1600, 2900)),
        ]
    )
    api.fakes.speech = speech
    api.container.voice_session._speech = speech  # the fixture wired the plain fake
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "teleprompter", "script": ROOFTOP, "keep_audio": True})
    for _ in range(2):
        await ws.send_bytes(FRAME)
    await ws.send_json({"type": "end"})
    events = await ws.until("session.ended")
    await ws.finish()

    assert [e["paragraph"] for e in events if e["type"] == "teleprompter.advanced"] == [1, 2]
    assert [t.text for t in api.project().turns] == ["Lena feeds the pigeons.", "A kite drifts down."]
    [narration] = api.project().narrations.values()
    assert narration.voice is None  # the reader's own voice


@pytest.mark.parametrize(
    ("start", "says"),
    [
        ({"mode": "read", "script": "x" * 4001}, "4,000 characters"),
        ({"mode": "teleprompter", "script": "  "}, "script"),
        ({"mode": "read", "script": ROOFTOP, "voice": "en-US-NobodyNeural"}, "voice"),
        ({"mode": "read", "script": ROOFTOP, "language": "hi-IN"}, "language"),  # the fake voice reads en and fr
    ],
)
async def test_a_script_or_voice_that_cannot_be_told_closes_with_a_clear_message(
    api: Api, start: dict[str, object], says: str
) -> None:
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json(start)
    error = await ws.receive()
    assert error is not None
    assert error["fatal"] is True
    assert says in error["message"]
    assert await ws.receive() is None
    assert ws.close_code == session.CLOSE_BAD_REQUEST


async def test_voices_lists_the_curated_set_with_languages_and_a_cached_preview(api: Api) -> None:
    body = (await api.client.get("/voices")).json()

    assert body["available"] is True
    assert body["default"] == AVA
    assert [v["name"] for v in body["voices"]] == [AVA, BRANDON]  # the default first
    voice = body["voices"][0]
    assert [x["locale"] for x in voice["languages"]] == ["en-US", "fr-FR"]

    first = await api.client.get(voice["preview_url"], params={"language": "fr-FR"})
    again = await api.client.get(voice["preview_url"], params={"language": "fr-FR"})
    assert (first.status_code, first.headers["content-type"]) == (200, "audio/wav")
    assert again.content == first.content
    assert len(api.fakes.synthesis.calls) == 1  # synthesized once, then kept
    assert (await api.client.get(f"/voices/{AVA}/preview", params={"language": "hi-IN"})).status_code == 422


async def test_without_text_to_speech_read_it_to_me_is_not_offered(make_api: Callable[..., Api], fakes: Fakes) -> None:
    fakes.tts = False
    api = make_api()
    assert (await api.client.get("/voices")).json() == {"available": False, "default": AVA, "voices": []}
    assert (await api.client.get(f"/voices/{BRANDON}/preview")).status_code == 503
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "read", "script": ROOFTOP})
    error = await ws.receive()
    assert error is not None
    assert "isn't available" in error["message"]
