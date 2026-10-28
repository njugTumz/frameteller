from frameteller.application.events import ShotUpdated
from frameteller.interface.dto import event_message
from tests.builders import shot


def test_a_reveal_reaches_clients_as_shot_updated() -> None:
    message = event_message(ShotUpdated(shot(3, "pip")))
    assert message["type"] == "shot.updated"
    assert message["shot"]["id"] == "s3"
    assert message["shot"]["character_ids"] == ["pip"]
