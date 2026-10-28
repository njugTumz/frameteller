from frameteller.application.use_cases import TranscribeInstruction
from frameteller.domain import TranscriptTurn
from tests.builders import project
from tests.fakes import FakeSpeechToText, InMemoryProjectRepository


async def test_a_spoken_instruction_becomes_text_biased_by_the_cast_names() -> None:
    speech = FakeSpeechToText(
        [TranscriptTurn("0", "make her raincoat ", 0, 900), TranscriptTurn("1", " red", 900, 1400)]
    )
    use_case = TranscribeInstruction(InMemoryProjectRepository(project()), speech)

    assert await use_case.execute("p1", b"RIFF-wav") == "make her raincoat red"
    assert speech.options is not None
    assert set(speech.options.keywords) == {"Mira", "Grey Cat"}
    assert bytes(speech.audio) == b"RIFF-wav"


async def test_silence_gives_empty_text() -> None:
    assert (
        await TranscribeInstruction(InMemoryProjectRepository(project()), FakeSpeechToText()).execute("p1", b"x") == ""
    )
