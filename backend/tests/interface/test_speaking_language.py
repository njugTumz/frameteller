"""The narrator's speaking language: passed to the transcriber as its language bias, auto when not chosen."""

import pytest

from frameteller.application.ports import SpeechMode
from frameteller.interface.dto import SPEAKING_LANGUAGES, SessionStart


@pytest.mark.parametrize(
    ("start", "bias"),
    [
        ({"mode": "narrate"}, None),  # auto: the transcriber detects it
        ({"mode": "narrate", "language": "ja-JP"}, "ja-JP"),
        ({"mode": "narrate", "language": "ko"}, "ko-KR"),
        ({"mode": "co_direct", "language": "zh-CN"}, "zh-CN"),
        ({"mode": "teleprompter", "script": "Hi.", "language": "hi-IN"}, "hi-IN"),
        ({"mode": "narrate", "language": "de-DE"}, None),  # not one we offer: auto
        ({"mode": "read", "script": "Hi.", "language": "ja-JP"}, None),  # a voice reads: nothing to transcribe
    ],
)
def test_the_chosen_language_becomes_the_transcribers_bias(start: dict[str, object], bias: str | None) -> None:
    options = SessionStart.model_validate(start).as_options()
    assert options.language_bias == bias
    assert options.mode is (SpeechMode.CO_DIRECTION if start["mode"] == "co_direct" else SpeechMode.NARRATION)


def test_the_speaking_languages_are_the_nine_we_offer() -> None:
    assert list(SPEAKING_LANGUAGES.values()) == [
        "en-US", "fr-FR", "es-ES", "pt-BR", "hi-IN", "ar-SA", "ja-JP", "ko-KR", "zh-CN",
    ]  # fmt: skip
