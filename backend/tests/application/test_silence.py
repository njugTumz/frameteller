"""We can't hear you: near-silent audio and no words at the start of a session."""

import struct

import pytest

from frameteller.application.events import NoSpeechHeard, SessionEnded
from frameteller.application.ports import PartialTranscript, SpeechOptions
from frameteller.application.use_cases.voice_session import SILENCE_WARNING_MS, pcm_level
from tests.application.test_beats import Session
from tests.fakes import LISTEN, FakeDirector, ScriptedSpeech

SECOND_OF_SILENCE = b"\x00\x00" * 24_000


def tone(amplitude: int) -> bytes:
    return struct.pack("<2h", amplitude, -amplitude) * 12_000  # one second


def test_pcm_level_is_rms_of_full_scale() -> None:
    assert pcm_level(b"") == 0.0
    assert pcm_level(SECOND_OF_SILENCE) == 0.0
    assert pcm_level(tone(16384)) == pytest.approx(0.5)
    assert pcm_level(b"\x01") == 0.0  # an odd trailing byte is ignored


async def run(chunks: list[bytes], script: list[object] | None = None) -> Session:
    speech = ScriptedSpeech(script or [LISTEN] * len(chunks))
    s = Session(speech, FakeDirector())
    await s.run.execute("p1", speech.paced(*chunks), SpeechOptions())
    return s


async def test_eight_silent_seconds_and_no_words_warn_once() -> None:
    s = await run([SECOND_OF_SILENCE] * 12)
    [warning] = s.events.of(NoSpeechHeard)
    assert warning == NoSpeechHeard(SILENCE_WARNING_MS, 0.0)
    [ended] = s.events.of(SessionEnded)
    assert ended == SessionEnded(0, 0, heard=False)


async def test_a_loud_microphone_without_words_does_not_warn() -> None:
    s = await run([tone(3000)] + [SECOND_OF_SILENCE] * 9)
    assert s.events.of(NoSpeechHeard) == []


async def test_words_before_eight_seconds_do_not_warn() -> None:
    script: list[object] = [LISTEN, PartialTranscript("Scene one"), *[LISTEN] * 9]
    s = await run([SECOND_OF_SILENCE] * 10, script)
    assert s.events.of(NoSpeechHeard) == []
    [ended] = s.events.of(SessionEnded)
    assert isinstance(ended, SessionEnded)
    assert ended.heard
