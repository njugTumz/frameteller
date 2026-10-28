from collections.abc import Callable

import pytest

from frameteller.application.errors import InvalidModelOutputError
from frameteller.application.ports import (
    AudioProgress,
    DirectedTurn,
    PartialTranscript,
    ShotDraft,
    SpeechEvent,
    TurnCompleted,
    TurnStarted,
)
from frameteller.domain import Character, Framing, Project, TranscriptTurn
from frameteller.interface.routes import session
from tests.builders import project
from tests.fakes import LISTEN, FakeDirector, ScriptedSpeech
from tests.interface.conftest import Api, Fakes, WsClient

OWL = Character("owl", "Owl", "a small brown owl with round spectacles")
TURN = TranscriptTurn("0", "An owl lands on the roof.", 0, 3000)
PATH = "/ws/projects/p1/session"
FRAME = b"\x00\x00" * 1920  # 80 ms at 24 kHz


def scripted(api: Api) -> None:
    p = project(approved=False, shots=0)
    p.bible.characters.clear()
    api.fakes.repo._data["p1"] = p
    events: list[SpeechEvent] = [
        TurnStarted("0", 0),
        PartialTranscript("An owl"),
        PartialTranscript("An owl lands on the roof"),
        TurnCompleted(TURN),
    ]
    api.fakes.speech.events = events
    shot = ShotDraft(Framing.WIDE, ("owl",), "a rooftop at night", "the owl lands", "", ("0",), 3000)
    api.fakes.director.turns = {"0": DirectedTurn((OWL,), (shot,))}


async def test_narration_becomes_partials_turns_shots_and_a_proposed_cast(api: Api) -> None:
    scripted(api)
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "narrate", "keywords": ["Owl", " Owl ", ""]})
    for _ in range(3):
        await ws.send_bytes(FRAME)
    await ws.send_json({"type": "end"})

    events = await ws.until("session.ended", "cast.proposed")
    types = [e["type"] for e in events]

    assert types[0] == "session.started"
    story = [t for t in types if t in ("transcript.partial", "turn.completed", "shot.created", "cast.proposed")]
    assert story == ["transcript.partial", "transcript.partial", "turn.completed", "shot.created", "cast.proposed"]
    by_type = {e["type"]: e for e in events}
    assert by_type["turn.completed"]["turn"] == {
        "id": "id1-0",  # the transcriber's turn 0, tagged with this session
        "text": "An owl lands on the roof.",
        "start_ms": 0,
        "end_ms": 3000,
        "speaker": None,
    }
    assert by_type["shot.created"]["shot"]["number"] == 1
    assert by_type["shot.created"]["shot"]["character_ids"] == ["owl"]
    [owl] = by_type["cast.proposed"]["characters"]
    assert owl["id"] == "owl"
    assert owl["reference_url"] == "/media/projects/p1/characters/owl/reference"
    assert by_type["session.ended"] == {"type": "session.ended", "turns": 1, "shots": 1, "heard": True}
    while not any(e["type"] == "job.updated" and e["status"] == "succeeded" for e in events):
        events.append(await ws.receive())  # type: ignore[arg-type]
    jobs = [(e["kind"], e["status"]) for e in events if e["type"] == "job.updated"]
    assert jobs == [("generate_cast", "queued"), ("generate_cast", "running"), ("generate_cast", "succeeded")]

    assert api.fakes.speech.options is not None
    assert api.fakes.speech.options.keywords == ("Owl",)
    assert len(api.fakes.speech.audio) == 3 * len(FRAME)
    await ws.finish()  # the client leaves; the server ends the session cleanly


async def test_one_live_session_per_project(api: Api) -> None:
    first = WsClient(api.app, PATH)
    assert await first.connect()
    await first.send_json({"mode": "narrate"})
    assert (await first.receive())["type"] == "session.started"  # type: ignore[index]

    second = WsClient(api.app, PATH)
    assert await second.connect()
    refused = await second.receive()
    assert refused == {
        "type": "error",
        "message": "A voice session is already running for this project.",
        "fatal": True,
    }
    assert await second.receive() is None
    assert second.close_code == session.CLOSE_BUSY

    await first.disconnect()
    await first.finish()
    third = WsClient(api.app, PATH)
    assert await third.connect()
    await third.send_json({"mode": "co_direct"})
    assert (await third.receive())["type"] == "session.started"  # type: ignore[index]
    await third.finish()


async def test_bad_start_message_closes_with_4400(api: Api) -> None:
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "sing"})
    error = await ws.receive()
    assert error is not None
    assert error["fatal"] is True
    assert await ws.receive() is None
    assert ws.close_code == session.CLOSE_BAD_REQUEST


async def test_bad_frames_are_dropped_with_one_notice(api: Api) -> None:
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "narrate"})
    await ws.send_bytes(b"\x00\x00\x00")  # odd length: not 16-bit PCM
    await ws.send_bytes(b"\x00" * (session.MAX_FRAME_BYTES + 2))
    await ws.send_bytes(FRAME)
    await ws.send_json({"type": "end"})

    events = await ws.until("session.ended")
    notices = [e for e in events if e["type"] == "error"]
    assert len(notices) == 1
    assert not notices[0]["fatal"]
    assert len(api.fakes.speech.audio) == len(FRAME)
    await ws.finish()


async def test_sessions_stop_at_the_length_limit(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session, "MAX_SESSION_MS", 100)
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "narrate"})
    await ws.send_bytes(FRAME)  # 80 ms
    await ws.send_bytes(FRAME)  # would pass 100 ms

    events = await ws.until("session.ended")
    assert any(e["type"] == "error" and "55 minutes" in e["message"] for e in events)
    assert len(api.fakes.speech.audio) == len(FRAME)
    await ws.finish()


async def test_unknown_project_and_foreign_origin_are_refused(make_api: Callable[..., Api]) -> None:
    api = make_api(allowed_origins="https://app.example")
    ws = WsClient(api.app, "/ws/projects/nope/session")
    assert await ws.connect()
    assert (await ws.receive())["message"] == "We couldn't find that project."  # type: ignore[index]
    assert await ws.receive() is None
    assert ws.close_code == session.CLOSE_NOT_FOUND

    foreign = WsClient(api.app, PATH, headers={"Origin": "https://evil.example"})
    assert not await foreign.connect()
    assert foreign.close_code == 1008
    ours = WsClient(api.app, PATH, headers={"Origin": "https://app.example"})
    assert await ours.connect()
    await ours.finish()


async def test_disconnect_mid_session_frees_the_project(api: Api) -> None:
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "narrate"})
    await ws.send_bytes(FRAME)
    await ws.disconnect()
    await ws.finish()
    assert api.container.sessions.claim("p1")


class ConfusedDirector(FakeDirector):
    async def direct_turn(self, turn: TranscriptTurn, project: Project) -> DirectedTurn:
        raise InvalidModelOutputError("muse-spark-1.3")


async def test_direction_failure_is_reported_and_the_session_goes_on(
    fakes: Fakes, make_api: Callable[..., Api]
) -> None:
    fakes.director = ConfusedDirector()
    api = make_api()
    scripted(api)
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "narrate"})
    await ws.send_json({"type": "end"})

    events = await ws.until("session.ended")

    message = "The director got confused by that line. Try saying it again."
    assert [e for e in events if e["type"] == "error"] == [{"type": "error", "message": message, "fatal": False}]
    assert events[-1] == {"type": "session.ended", "turns": 1, "shots": 0, "heard": True}
    await ws.finish()


async def test_closing_a_socket_the_client_already_left_does_not_raise() -> None:
    from frameteller.interface.routes.session import _close

    class Gone:
        async def close(self, code: int) -> None:
            raise OSError("client disconnected")

    await _close(Gone(), 1000)  # type: ignore[arg-type]


async def test_beats_cut_shots_and_corrections_redirect_them(fakes: Fakes, make_api: Callable[..., Api]) -> None:
    speech = ScriptedSpeech(
        [
            LISTEN,
            TurnStarted("0", 0),
            PartialTranscript("An owl lands"),
            LISTEN,
            AudioProgress(600),  # 500 ms past the beat at 80 ms: it closes here
            PartialTranscript("An owl lands it hoots"),
            TurnCompleted(TranscriptTurn("0", "An owl lands it hoots", 0, 160)),
        ]
    )
    fakes.speech = speech
    api = make_api()
    scripted(api)
    shot = ShotDraft(Framing.WIDE, ("owl",), "a rooftop", "the owl hoots", "", ("?",), 1)
    api.fakes.director.turns |= {"b1": api.fakes.director.turns["0"], "b2": DirectedTurn((), (shot,))}

    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "narrate"})
    for message in (FRAME, {"type": "beat"}, {"type": "nonsense"}, FRAME, {"type": "end"}):
        await speech.listening.wait()
        if isinstance(message, bytes):
            speech.listening.clear()
            await ws.send_bytes(message)
        else:
            await ws.send_json(message)
    events = await ws.until("session.ended")

    turns = [e["turn"] for e in events if e["type"] == "turn.completed"]
    assert [(t["text"], t["start_ms"], t["end_ms"]) for t in turns] == [("An owl lands", 0, 80), ("it hoots", 80, 160)]
    shots = [e["shot"] for e in events if e["type"] == "shot.created"]
    assert [s["number"] for s in shots] == [1, 2]
    [notice] = [e for e in events if e["type"] == "error"]
    assert "Unknown message" in notice["message"]
    assert not notice["fatal"]

    # After the narration, the socket stays open for corrections.
    await ws.send_json({"type": "transcript.corrected", "turn_id": turns[1]["id"], "text": "It hoots twice."})
    [replaced] = [e for e in await ws.until("shots.replaced") if e["type"] == "shots.replaced"]
    assert replaced["turn"]["text"] == "It hoots twice."
    assert replaced["removed_shot_ids"] == [shots[1]["id"]]
    assert [s["number"] for s in replaced["shots"]] == [2]
    assert replaced["shots"][0]["duration_ms"] == 80
    await ws.send_json({"type": "transcript.corrected", "turn_id": "nope", "text": "x"})
    error = await ws.receive()
    assert error is not None
    assert error["type"] == "error"
    await ws.finish()


async def test_the_recording_is_kept_when_the_client_asks(api: Api) -> None:
    scripted(api)
    ws = WsClient(api.app, PATH)
    assert await ws.connect()
    await ws.send_json({"mode": "narrate", "keep_audio": True})
    for _ in range(2):
        await ws.send_bytes(FRAME)
    await ws.send_json({"type": "end"})
    await ws.until("session.ended")
    await ws.finish()

    [narration] = api.project().narrations.values()
    assert narration.duration_ms == 160
    data, kind = api.fakes.storage.files[narration.recording.key]
    assert kind == "audio/wav"
    assert data[44:] == FRAME * 2
