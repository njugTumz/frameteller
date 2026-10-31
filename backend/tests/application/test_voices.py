"""The voices "Read it to me" offers: each lists only the languages Azure says it speaks, in our order."""

import pytest

from frameteller.application.errors import ScriptError
from frameteller.application.ports import SpokenClip, Voice
from frameteller.application.use_cases.voices import CURATED, DEFAULT_VOICE, LANGUAGES, ListVoices, offered

ALL = tuple(locale for locale, _ in LANGUAGES.values())


def voice(name: str, *speaks: str) -> Voice:
    accent = name[:5]
    return Voice(
        name,
        name.split("-")[2].removesuffix("MultilingualNeural") + " Multilingual",
        "Female",
        accent,
        (accent, *speaks),
    )


class Speech:
    def __init__(self, voices: list[Voice]) -> None:
        self._voices = voices

    async def voices(self) -> list[Voice]:
        return self._voices

    async def synthesize(self, text: str, voice: str, language: str, store_as: str) -> SpokenClip:
        raise AssertionError("listing voices speaks nothing")


def test_the_languages_are_named_in_their_own_words_in_our_order() -> None:
    names = [name for _, name in LANGUAGES.values()]
    assert names == ["English", "Français", "Español", "Português", "हिन्दी", "العربية", "日本語", "한국어", "中文"]


def test_a_language_is_hidden_for_a_voice_that_does_not_speak_it() -> None:
    full = voice(CURATED[1], *ALL)
    partial = voice(CURATED[2], "fr-FR", "ja-JP")  # no Korean, no Chinese
    listed = offered([partial, full, voice("en-US-SomeoneElseNeural", *ALL)])
    assert [v.name for v in listed] == [CURATED[1], CURATED[2]]  # curated only, in our order
    assert [x.code for x in listed[0].languages] == ["en", "fr", "es", "pt", "hi", "ar", "ja", "ko", "zh"]
    assert [x.code for x in listed[1].languages] == ["en", "fr", "ja"]
    assert listed[1].languages[2].name == "日本語"


async def test_a_session_may_only_ask_a_voice_for_a_language_it_offers() -> None:
    voices = ListVoices(Speech([voice(DEFAULT_VOICE, *ALL), voice(CURATED[2], "ja-JP")]))
    assert (await voices.check(DEFAULT_VOICE, "zh-CN")).locale == "zh-CN"
    assert (await voices.check(DEFAULT_VOICE, "ko")).locale == "ko-KR"
    assert (await voices.check(CURATED[2], "ja-JP")).name == "日本語"
    with pytest.raises(ScriptError, match="doesn't read that language"):
        await voices.check(CURATED[2], "zh-CN")
