from frameteller.application.events import ShotUpdated
from frameteller.interface.dto import event_message
from tests.builders import shot


def test_a_reveal_reaches_clients_as_shot_updated() -> None:
    message = event_message(ShotUpdated(shot(3, "pip")))
    assert message["type"] == "shot.updated"
    assert message["shot"]["id"] == "s3"
    assert message["shot"]["character_ids"] == ["pip"]


def test_silence_and_an_empty_session_reach_clients() -> None:
    from frameteller.application.events import NoSpeechHeard, SessionEnded

    assert event_message(NoSpeechHeard(8000, 0.001)) == {"type": "audio.silent", "after_ms": 8000, "level": 0.001}
    assert event_message(SessionEnded(0, 0, heard=False)) == {
        "type": "session.ended",
        "turns": 0,
        "shots": 0,
        "heard": False,
    }
