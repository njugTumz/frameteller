"""Teleprompter sessions (ADR 0015): the reader's paragraphs become turns, cut when they finish and pause."""

from frameteller.application.events import ScriptAccepted, TeleprompterAdvanced
from frameteller.application.ports import (
    AudioProgress,
    PartialTranscript,
    SpeechOptions,
    TurnCompleted,
    TurnEnded,
    TurnStarted,
)
from frameteller.application.use_cases import Beat
from frameteller.domain import ScriptFormat, TranscriptTurn, parse_script
from tests.application.test_beats import CHUNK, Session, one_shot
from tests.fakes import LISTEN, FakeDirector, ScriptedSpeech

SCRIPT = parse_script("Wide shot. Lena feeds the pigeons on the roof.\n\nA paper kite drifts down into her hands.")


def turns(s: Session) -> list[tuple[str, str, int, int, str]]:
    return [(t.id, t.text, t.start_ms, t.end_ms, t.direction) for t in s.repo.peek("p1").turns]


def advanced(s: Session) -> list[int]:
    return [e.paragraph for e in s.events.of(TeleprompterAdvanced) if isinstance(e, TeleprompterAdvanced)]


async def test_a_paragraph_read_to_its_end_is_cut_at_the_pause_even_when_words_were_misheard() -> None:
    speech = ScriptedSpeech(
        [
            TurnStarted("0", 200),
            PartialTranscript("Lina feeds the pigeon on the ruf"),
            AudioProgress(2600),  # the end is heard here
            LISTEN,
            TurnEnded("0", 2400),  # the transcriber hears the pause
            TurnCompleted(TranscriptTurn("0", "Lina feeds the pigeon on the ruf", 200, 2400)),
            TurnStarted("1", 3500),
            PartialTranscript("A paper kite drifts down into her hands"),
            AudioProgress(5600),
            TurnEnded("1", 5300),
            TurnCompleted(TranscriptTurn("1", "A paper kite drifts down into her hands", 3500, 5300)),
        ]
    )
    s = Session(speech, FakeDirector({"b1": one_shot(), "b2": one_shot()}))

    await s.run.execute("p1", speech.paced(CHUNK, CHUNK), SpeechOptions(), script=SCRIPT)

    assert turns(s) == [
        # The script's words for captions; its cue goes to the director. The transcriber's turns direct nothing.
        ("s1-b1", "Lena feeds the pigeons on the roof.", 200, 2600, "Wide shot. Lena feeds the pigeons on the roof."),
        ("s1-b2", "A paper kite drifts down into her hands.", 3500, 5600, "A paper kite drifts down into her hands."),
    ]
    assert s.director.calls == ["b1", "b2"]
    assert advanced(s) == [1, 2]
    [accepted] = s.events.of(ScriptAccepted)
    assert isinstance(accepted, ScriptAccepted)
    assert accepted.script == SCRIPT


async def test_reading_straight_on_cuts_at_the_end_of_the_paragraph_and_keeps_the_rest() -> None:
    speech = ScriptedSpeech(
        [
            TurnStarted("0", 0),
            AudioProgress(2500),
            PartialTranscript("Lena feeds the pigeons on the roof a paper kite"),  # no pause between paragraphs
            LISTEN,
            AudioProgress(4000),
            PartialTranscript("Lena feeds the pigeons on the roof a paper kite drifts down into her hands"),
            TurnEnded("0", 4200),
            TurnCompleted(TranscriptTurn("0", "x", 0, 4200)),
        ]
    )
    s = Session(speech, FakeDirector({"b1": one_shot(), "b2": one_shot()}))

    await s.run.execute("p1", speech.paced(CHUNK), SpeechOptions(), script=SCRIPT)

    assert [(t[1], t[2], t[3]) for t in turns(s)] == [
        ("Lena feeds the pigeons on the roof.", 0, 2500),
        ("A paper kite drifts down into her hands.", 2500, 4200),  # its first words were heard at the cut
    ]


async def test_space_cuts_by_hand_but_space_right_after_an_automatic_cut_only_confirms_it() -> None:
    speech = ScriptedSpeech(
        [
            TurnStarted("0", 0),
            PartialTranscript("Lena feeds the pigeons on the roof"),
            AudioProgress(2500),
            TurnEnded("0", 2300),  # automatic cut at 2500
            TurnCompleted(TranscriptTurn("0", "Lena feeds the pigeons on the roof", 0, 2300)),
            LISTEN,
            AudioProgress(3100),  # the reader's habitual Space at 2600 closes nothing: a confirmation
            TurnStarted("1", 3200),
            PartialTranscript("A paper kite"),
            LISTEN,
            AudioProgress(5000),  # Space at 4400, mid-paragraph: the reader moves on by hand
            TurnEnded("1", 4300),
        ]
    )
    s = Session(speech, FakeDirector({"b1": one_shot(), "b2": one_shot()}))

    await s.run.execute("p1", speech.paced(CHUNK, Beat(2600), CHUNK, Beat(4400), CHUNK), SpeechOptions(), script=SCRIPT)

    assert [(t[1], t[2], t[3]) for t in turns(s)] == [
        ("Lena feeds the pigeons on the roof.", 0, 2500),
        ("A paper kite drifts down into her hands.", 3200, 4400),
    ]
    assert advanced(s) == [1, 2]


async def test_episodes_follow_the_script_and_the_shot_limit_counts_per_episode() -> None:
    script = parse_script("Episode 1\n\nLena waves.\n\nEpisode 2\n\nThe kite returns.", ScriptFormat.TEXT)
    speech = ScriptedSpeech(
        [
            TurnStarted("0", 0),
            PartialTranscript("Lena waves"),
            AudioProgress(1500),
            TurnEnded("0", 1200),
            LISTEN,
            TurnStarted("1", 2000),
            PartialTranscript("The kite returns"),
            AudioProgress(3500),
            TurnEnded("1", 3200),
        ]
    )
    s = Session(speech, FakeDirector({"b1": one_shot(), "b2": one_shot()}))

    await s.run.execute("p1", speech.paced(CHUNK, CHUNK), SpeechOptions(), script=script)

    assert [t.episode for t in s.repo.peek("p1").turns] == [1, 2]
    assert [(sh.number, sh.episode) for sh in s.shots()] == [(1, 1), (2, 2)]
