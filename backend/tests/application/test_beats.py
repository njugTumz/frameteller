"""Beats, the duration split and transcript corrections (ADR 0008), with a speech fake scripted in step with audio."""

from frameteller.application.events import SessionFailed, ShotCreated, ShotsReplaced, TranscriptUpdated, TurnFinished
from frameteller.application.ports import (
    AudioProgress,
    DirectedTurn,
    PartialTranscript,
    ShotDraft,
    SpeechOptions,
    TurnCompleted,
    TurnEnded,
    TurnStarted,
)
from frameteller.application.use_cases import (
    Beat,
    CorrectTranscript,
    DirectTurn,
    RequestCastReferences,
    RunVoiceSession,
    TranscriptCorrection,
)
from frameteller.domain import Character, Framing, MediaRef, Project, Shot, Size, TranscriptTurn
from tests.builders import project
from tests.fakes import (
    LISTEN,
    FakeDirector,
    InMemoryJobQueue,
    InMemoryMediaStorage,
    InMemoryProjectRepository,
    RecordingPublisher,
    ScriptedSpeech,
    SequentialIds,
)

CHUNK = b"\x00\x00" * 1920
OWL = Character("owl", "Owl", "a small brown owl with round spectacles")


def draft(action: str, *characters: str) -> ShotDraft:
    return ShotDraft(Framing.MEDIUM, characters or ("mira",), "a narrow alley", action, "", ("?",), 1)


def one_shot(action: str = "Mira walks") -> DirectedTurn:
    return DirectedTurn((), (draft(action),))


class Session:
    def __init__(
        self, speech: ScriptedSpeech, director: FakeDirector, shots: int = 0, story: Project | None = None
    ) -> None:
        self.repo = InMemoryProjectRepository(story or project(shots=shots))
        self.events, self.jobs = RecordingPublisher(), InMemoryJobQueue()
        self.storage = InMemoryMediaStorage()
        self.director = director
        cast = RequestCastReferences(self.repo, self.jobs, SequentialIds("n"))
        self.run = RunVoiceSession(
            speech,
            DirectTurn(self.repo, director, SequentialIds("shot")),
            CorrectTranscript(self.repo, director, SequentialIds("fix"), cast, self.events),
            cast,
            self.events,
            SequentialIds("s"),
            self.repo,
            self.storage,
        )

    def turns(self) -> list[tuple[str, str, int, int]]:
        return [(t.id, t.text, t.start_ms, t.end_ms) for t in self.repo.peek("p1").turns]

    def shots(self) -> list[Shot]:
        return self.repo.peek("p1").shots


async def test_beats_cut_shots_at_the_words_heard_so_far_and_the_audio_position() -> None:
    speech = ScriptedSpeech(
        [
            LISTEN,
            AudioProgress(900),  # the first beat closes with nothing said: it only marks the start
            TurnStarted("0", 500),
            PartialTranscript("Night in the alley"),
            LISTEN,
            AudioProgress(4300),  # not yet 500 ms past the beat at 4000
            PartialTranscript("Night in the alley tonight"),  # a word that was still in flight at the beat
            AudioProgress(4500),
            PartialTranscript("Night in the alley tonight she hears a sound"),
            TurnEnded("0", 9000),
            TurnCompleted(TranscriptTurn("0", "Night in the alley tonight she hears a sound", 500, 9000)),
            LISTEN,
            AudioProgress(9700),
            TurnStarted("1", 9500),
            PartialTranscript("Close on the crate"),
            TurnEnded("1", 12000),
            TurnCompleted(TranscriptTurn("1", "Close on the crate a cat", 9500, 12000)),
        ]
    )
    director = FakeDirector({"b1": one_shot(), "b2": one_shot(), "b3": one_shot()})
    s = Session(speech, director)

    ended = await s.run.execute(
        "p1", speech.paced(Beat(400), CHUNK, Beat(4000), CHUNK, Beat(9200), CHUNK), SpeechOptions()
    )

    assert s.turns() == [
        ("s1-b1", "Night in the alley tonight", 500, 4000),  # from the first speech, not the beat at 400
        ("s1-b2", "she hears a sound", 4000, 9200),  # split inside one transcriber turn: speech never stopped
        ("s1-b3", "Close on the crate a cat", 9500, 12000),  # the pause after the beat at 9200 is trimmed
    ]
    assert director.calls == ["b1", "b2", "b3"]  # the transcriber's own turns were never directed
    assert [s.duration_ms for s in s.shots()] == [3500, 5200, 2500]
    assert (ended.turns, ended.shots) == (3, 3)
    assert [e.turn.id for e in s.events.of(TurnFinished) if isinstance(e, TurnFinished)] == ["s1-b1", "s1-b2", "s1-b3"]
    # The live line holds only the words not yet in a beat, so the UI never shows a word twice.
    assert [e.text for e in s.events.of(TranscriptUpdated) if isinstance(e, TranscriptUpdated)] == [
        "Night in the alley",
        "Night in the alley tonight",
        "",
        "she hears a sound",
        "",
        "Close on the crate",
        "",
    ]


async def test_a_later_speech_complete_never_directs_the_same_audio_twice() -> None:
    speech = ScriptedSpeech(
        [
            TurnStarted("0", 0),
            PartialTranscript("An owl lands"),
            TurnCompleted(TranscriptTurn("0", "An owl lands", 0, 2000)),  # before any beat: endpointing directs it
            LISTEN,
            TurnStarted("1", 2500),
            PartialTranscript("It hoots"),
            LISTEN,
            AudioProgress(4500),
            TurnCompleted(TranscriptTurn("1", "It hoots twice", 2500, 5000)),  # after a beat: not directed
        ]
    )
    director = FakeDirector({"0": one_shot(), "b1": one_shot(), "b2": one_shot()})
    s = Session(speech, director)

    await s.run.execute("p1", speech.paced(CHUNK, Beat(4000), CHUNK), SpeechOptions())

    assert director.texts == ["An owl lands", "It hoots", "twice"]
    assert s.turns() == [
        ("s1-0", "An owl lands", 0, 2000),
        ("s1-b1", "It hoots", 2500, 4000),  # spoken from 2500: the pause after the first turn is trimmed
        ("s1-b2", "twice", 4000, 5000),
    ]
    assert len(s.events.of(ShotCreated)) == 3


async def test_a_long_silence_before_the_first_words_is_not_part_of_the_shot() -> None:
    """A narrator pressed beat at 66 s, then said nothing until 105 s: the first shot lasted 49 s."""
    speech = ScriptedSpeech(
        [
            LISTEN,
            LISTEN,
            AudioProgress(66_600),  # the beat at 66 s closes with nothing said
            TurnStarted("0", 105_000),
            PartialTranscript("A tiny lighthouse on a rock"),
            LISTEN,
            LISTEN,
            TurnEnded("0", 114_000),
            TurnCompleted(TranscriptTurn("0", "A tiny lighthouse on a rock", 105_000, 114_000)),
            AudioProgress(115_600),  # closes the beat at 115 s
            TurnStarted("1", 116_000),
            PartialTranscript("Inside an old woman"),
            TurnEnded("1", 120_000),
            LISTEN,
        ]
    )
    director = FakeDirector({"b1": one_shot(), "b2": one_shot()})
    s = Session(speech, director)

    await s.run.execute(
        "p1", speech.paced(CHUNK, Beat(66_000), CHUNK, CHUNK, Beat(115_000), CHUNK, CHUNK), SpeechOptions()
    )

    assert [(t[2], t[3]) for t in s.turns()] == [(105_000, 115_000), (116_000, 120_000)]
    assert [shot.duration_ms for shot in s.shots()] == [10_000, 4_000]


async def test_without_beats_the_transcriber_turns_cut_the_shots() -> None:
    t0, t1 = TranscriptTurn("0", "An owl lands", 0, 2000), TranscriptTurn("1", "It hoots", 2500, 5000)
    speech = ScriptedSpeech([TurnCompleted(t0), LISTEN, TurnCompleted(t1)])
    director = FakeDirector({"0": one_shot(), "1": one_shot()})
    s = Session(speech, director)

    await s.run.execute("p1", speech.paced(CHUNK), SpeechOptions())

    assert s.turns() == [("s1-0", "An owl lands", 0, 2000), ("s1-1", "It hoots", 2500, 5000)]


async def test_one_turn_shares_its_time_by_word_count_and_adds_up() -> None:
    repo = InMemoryProjectRepository(project(shots=0))
    turn = TranscriptTurn("t1", "a long line", 1000, 11000)
    drafts = (
        draft("Mira walks down the long rainy alley towards home alone"),  # 10 words
        draft("She stops"),
        draft("Listens"),
    )
    director = FakeDirector({"t1": DirectedTurn((), drafts)})

    directed = await DirectTurn(repo, director, SequentialIds("shot")).execute("p1", turn)

    durations = [s.duration_ms for s in directed.shots]
    assert sum(durations) == turn.duration_ms
    assert min(durations) >= 1500
    assert durations == [7000, 1500, 1500]


def correction_world() -> tuple[CorrectTranscript, InMemoryProjectRepository, FakeDirector, RecordingPublisher]:
    p = project()  # turns t1..t3, one shot each
    p.panel("s2").record_render(1, MediaRef("projects/p1/panels/s2/r1/image"), "resp", Size(1920, 1280))
    repo = InMemoryProjectRepository(p)
    director = FakeDirector({"t2": DirectedTurn((OWL,), (draft("The owl lands", "owl"), draft("Mira looks up")))})
    events = RecordingPublisher()
    cast = RequestCastReferences(repo, InMemoryJobQueue(), SequentialIds("n"))
    return CorrectTranscript(repo, director, SequentialIds("fix"), cast, events), repo, director, events


async def test_a_correction_redirects_only_the_shots_from_that_turn() -> None:
    correct, repo, director, events = correction_world()

    replaced = await correct.execute("p1", "t2", "An owl lands, and Mira looks up.")

    p = repo.peek("p1")
    assert [(s.id, s.number) for s in p.shots] == [("s1", 1), ("fix1", 2), ("fix2", 3), ("s3", 4)]
    assert p.turn("t2").text == "An owl lands, and Mira looks up."
    assert director.texts == ["An owl lands, and Mira looks up."]
    assert "s2" not in p.panels  # it showed the misheard line
    assert "owl" in p.bible
    assert replaced.removed_shot_ids == ("s2",)
    assert [s.number for s in replaced.shots] == [2, 3]
    assert sum(s.duration_ms for s in replaced.shots) == p.turn("t2").duration_ms
    assert events.of(ShotsReplaced) == [replaced]


async def test_corrections_in_a_session_run_after_the_shots_they_fix() -> None:
    speech = ScriptedSpeech([TurnCompleted(TranscriptTurn("0", "Sinuan night", 0, 3000)), LISTEN])
    director = FakeDirector({"0": one_shot(), "b": one_shot()})
    s = Session(speech, director)

    await s.run.execute(
        "p1",
        speech.paced(TranscriptCorrection("s1-0", "Scene one. Night."), TranscriptCorrection("s1-9", "x"), CHUNK),
        SpeechOptions(),
    )

    assert director.texts == ["Sinuan night", "Scene one. Night."]
    assert s.turns() == [("s1-0", "Scene one. Night.", 0, 3000)]
    [shot] = s.shots()
    assert shot.id == "fix1"
    [failure] = s.events.of(SessionFailed)
    assert isinstance(failure, SessionFailed)
    assert "correction" in failure.message


async def test_beats_still_waiting_when_the_stream_ends_close_in_order() -> None:
    speech = ScriptedSpeech([PartialTranscript("one two"), LISTEN, PartialTranscript("one two three")])
    director = FakeDirector({"b1": one_shot(), "b2": one_shot()})
    s = Session(speech, director)

    await s.run.execute("p1", speech.paced(Beat(1000), CHUNK), SpeechOptions())

    # No progress events at all (another adapter, or a short stream): the beat closes when the transcript ends.
    assert s.turns() == [("s1-b1", "one two three", 0, 1000)]
