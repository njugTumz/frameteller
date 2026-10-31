"""Keeping the narrator's recording only with consent, and deleting it."""

from frameteller.application.audio import wav_bytes
from frameteller.application.ports import SpeechOptions
from frameteller.application.use_cases import DeleteNarration
from frameteller.domain import MediaRef, Narration, session_of
from tests.application.test_beats import CHUNK, Session
from tests.fakes import LISTEN, FakeDirector, ScriptedSpeech


async def narrate(*, keep_audio: bool, language: str | None = None) -> Session:
    speech = ScriptedSpeech([LISTEN, LISTEN])
    s = Session(speech, FakeDirector())
    options = SpeechOptions(language_bias=language)
    await s.run.execute("p1", speech.paced(CHUNK, CHUNK), options, keep_audio=keep_audio)
    return s


def test_wav_bytes_has_a_canonical_header() -> None:
    wav = wav_bytes(b"\x01\x00\x02\x00\x03")
    assert wav[:4] == b"RIFF"
    assert wav[8:16] == b"WAVEfmt "
    assert int.from_bytes(wav[24:28], "little") == 24_000
    assert int.from_bytes(wav[40:44], "little") == 4  # the odd byte is dropped
    assert len(wav) == 48


async def test_the_recording_is_kept_only_when_the_narrator_agreed() -> None:
    assert (await narrate(keep_audio=False)).storage.files == {}

    s = await narrate(keep_audio=True)
    [(key, (data, kind))] = s.storage.files.items()
    assert key == "projects/p1/narration/s1.wav"
    assert kind == "audio/wav"
    assert data == wav_bytes(CHUNK * 2)
    assert s.repo.peek("p1").narrations == {"s1": Narration("s1", MediaRef(key), 160)}  # two 80 ms chunks
    assert session_of("s1-b3") == "s1"


async def test_the_kept_recording_remembers_the_language_the_narrator_chose() -> None:
    s = await narrate(keep_audio=True, language="ja-JP")
    assert s.repo.peek("p1").narrations["s1"].language == "ja-JP"  # the captions' language at export


async def test_delete_my_recording_removes_the_files_and_the_references() -> None:
    s = await narrate(keep_audio=True)
    project = await DeleteNarration(s.repo, s.storage).execute("p1")
    assert project.narrations == {}
    assert s.repo.peek("p1").narrations == {}
    assert s.storage.files == {}
