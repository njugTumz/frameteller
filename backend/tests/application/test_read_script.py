""" "Read it to me" (ADR 0015): a voice reads the script, the animatic is timed to its audio, episodes pause."""

import asyncio
import io
import wave
from collections.abc import AsyncIterator

import pytest

from frameteller.application import costs
from frameteller.application.events import (
    ParagraphVoiced,
    ReadingPaused,
    ReadingResumed,
    ScriptAccepted,
    SessionEnded,
    SessionFailed,
)
from frameteller.application.limits import DemoLimits, SpeechAllowance
from frameteller.application.use_cases import (
    CorrectTranscript,
    DirectTurn,
    ReadControl,
    ReadingOptions,
    ReadScript,
    RequestCastReferences,
    StoryDirector,
)
from frameteller.application.use_cases.read_script import speech_key
from frameteller.domain import MediaRef, PanelStatus, Project, parse_script
from frameteller.domain.panels import Panel
from tests.application.test_beats import one_shot
from tests.builders import project
from tests.fakes import (
    FakeDirector,
    FakeSpeechSynthesis,
    FakeTranslator,
    FixedClock,
    InMemoryJobQueue,
    InMemoryMediaStorage,
    InMemoryProjectRepository,
    InMemoryVisitorQuota,
    RecordingBudget,
    RecordingPublisher,
    SequentialIds,
)

ROOFTOP = parse_script("Wide shot. Lena feeds the pigeons.\n\nA kite drifts down.")
BRANDON = "en-US-BrandonMultilingualNeural"
EPISODES = parse_script("Episode 1\n\nLena waves.\n\nEpisode 2\n\nThe kite returns.")


async def no_controls() -> AsyncIterator[ReadControl]:
    await asyncio.Event().wait()  # the listener never presses anything
    yield "continue"


class Reading:
    def __init__(self, *, translator: FakeTranslator | None = None, per_visitor: int = 12_000) -> None:
        self.repo = InMemoryProjectRepository(project(shots=0))
        self.events, self.jobs = RecordingPublisher(), InMemoryJobQueue()
        self.storage = InMemoryMediaStorage()
        self.speech = FakeSpeechSynthesis(self.storage)
        self.translator = translator or FakeTranslator()
        self.budget = RecordingBudget()
        self.director = FakeDirector({"b1": one_shot(), "b2": one_shot(), "b3": one_shot()})
        self.sleeps: list[float] = []
        self.on_sleep: list[object] = []  # callbacks run on each sleep, for tests that act "meanwhile"
        cast = RequestCastReferences(self.repo, self.jobs, SequentialIds("n"))
        story = StoryDirector(
            DirectTurn(self.repo, self.director, SequentialIds("shot")),
            CorrectTranscript(self.repo, self.director, SequentialIds("fix"), cast, self.events),
            cast,
            self.events,
        )
        limits = DemoLimits(speech_characters_per_visitor_per_day=per_visitor)
        allowance = SpeechAllowance(InMemoryVisitorQuota(), FixedClock(), limits, per_day=200_000)
        self.run = ReadScript(
            self.speech,
            self.translator,
            story,
            self.events,
            SequentialIds("r"),
            self.repo,
            self.storage,
            self.budget,
            allowance,
            sleep=self.sleep,
        )

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        for act in list(self.on_sleep):
            act()  # type: ignore[operator]
        await asyncio.sleep(0)

    def project(self) -> Project:
        return self.repo.peek("p1")

    def voiced(self) -> list[ParagraphVoiced]:
        return [e for e in self.events.of(ParagraphVoiced) if isinstance(e, ParagraphVoiced)]


def ms(text: str) -> int:
    return len(text) * 10  # the fake speaks 10 ms per character


async def test_each_paragraph_is_voiced_and_its_turn_lasts_as_long_as_its_audio() -> None:
    r = Reading()

    ended = await r.run.execute("p1", ROOFTOP, ReadingOptions(BRANDON, "en-US", "v1"), no_controls())

    first, second = "Lena feeds the pigeons.", "A kite drifts down."
    turns = [(t.id, t.text, t.start_ms, t.end_ms, t.direction) for t in r.project().turns]
    assert turns == [
        ("r1-b1", first, 0, ms(first), "Wide shot. Lena feeds the pigeons."),  # the cue goes to the director
        ("r1-b2", second, ms(first), ms(first) + ms(second), "A kite drifts down."),
    ]
    assert [(v.paragraph, v.episode, v.text, v.duration_ms) for v in r.voiced()] == [
        (0, 1, first, ms(first)),
        (1, 1, second, ms(second)),
    ]
    assert r.speech.calls == [(first, BRANDON, "en-US"), (second, BRANDON, "en-US")]
    assert r.translator.calls == []  # English is read as written
    assert r.budget.total == pytest.approx(costs.tts(len(first) + len(second)))
    assert ended == SessionEnded(2, 2, True)
    assert len(r.events.of(ScriptAccepted)) == 1
    # The kept narration is the whole reading, in the chosen voice: the animatic's voice track.
    [narration] = r.project().narrations.values()
    assert (narration.voice, narration.language, narration.duration_ms) == (BRANDON, "en-US", ms(first + second))
    with wave.open(io.BytesIO(await r.storage.get(narration.recording))) as w:
        assert w.getnframes() * 1000 // w.getframerate() == ms(first + second)


async def test_synthesis_stays_one_paragraph_ahead_of_playback() -> None:
    r = Reading()

    await r.run.execute("p1", ROOFTOP, ReadingOptions(BRANDON, "en-US"), no_controls())

    # The second paragraph is voiced at once; nothing waits while the first plays from the start.
    assert r.sleeps == [0, max(0, ms("Lena feeds the pigeons.") - 1500) / 1000]


async def test_the_same_words_in_the_same_voice_are_never_synthesized_or_paid_twice() -> None:
    r = Reading()
    await r.run.execute("p1", ROOFTOP, ReadingOptions(BRANDON, "en-US"), no_controls())
    paid, spoken = r.budget.total, len(r.speech.calls)

    await r.run.execute("p1", ROOFTOP, ReadingOptions(BRANDON, "en-US"), no_controls())

    assert (r.budget.total, len(r.speech.calls)) == (paid, spoken)
    assert speech_key("p1", "A kite drifts down.", BRANDON, "en-US") != speech_key(
        "p1", "A kite drifts down.", BRANDON, "fr-FR"
    )


async def test_another_language_is_translated_first_and_the_director_keeps_the_original_meaning() -> None:
    r = Reading()

    await r.run.execute("p1", ROOFTOP, ReadingOptions(BRANDON, "fr-FR"), no_controls())

    assert r.translator.calls == [(["Lena feeds the pigeons.", "A kite drifts down."], "fr-FR")]
    [first, _] = r.project().turns
    assert first.text == "[fr-FR] Lena feeds the pigeons."  # what the voice said, for the transcript rail
    assert first.direction == "Wide shot. Lena feeds the pigeons."
    assert r.director.texts[0] == "[fr-FR] Lena feeds the pigeons."
    assert [(v.text, v.original) for v in r.voiced()][1] == ("[fr-FR] A kite drifts down.", "A kite drifts down.")
    assert r.speech.calls[0] == ("[fr-FR] Lena feeds the pigeons.", BRANDON, "fr-FR")


async def test_a_failed_translation_reads_the_script_as_written_and_says_so() -> None:
    r = Reading(translator=FakeTranslator(fail=True))

    await r.run.execute("p1", ROOFTOP, ReadingOptions(BRANDON, "fr-FR"), no_controls())

    assert [t.text for t in r.project().turns] == ["Lena feeds the pigeons.", "A kite drifts down."]
    assert any(isinstance(e, SessionFailed) and "translate" in e.message for e in r.events.of(SessionFailed))


async def test_the_daily_speech_cap_stops_the_reading_before_anything_is_paid() -> None:
    r = Reading(per_visitor=30)  # enough for the first paragraph only

    ended = await r.run.execute("p1", ROOFTOP, ReadingOptions(BRANDON, "en-US", "v1"), no_controls())

    assert len(r.speech.calls) == 1
    assert r.budget.total == pytest.approx(costs.tts(len("Lena feeds the pigeons.")))
    fatal = [e for e in r.events.of(SessionFailed) if isinstance(e, SessionFailed) and e.fatal]
    assert len(fatal) == 1
    assert "characters read aloud today" in fatal[0].message
    assert ended.turns == 1


async def test_between_episodes_the_reading_waits_for_the_drafts_then_goes_on_by_itself() -> None:
    r = Reading()

    def draw_episode_one() -> None:
        # The studio draws episode 1's drafts while the reading waits.
        if len(r.events.of(ReadingPaused)) and r.project().shots:
            shot = r.project().shots[0]

            def drawn(p: Project) -> None:
                p.panels[shot.id] = Panel(shot.id, 1, PanelStatus.READY, MediaRef("x.webp"))

            asyncio.get_running_loop().create_task(r.repo.update("p1", drawn))

    r.on_sleep.append(draw_episode_one)

    await r.run.execute("p1", EPISODES, ReadingOptions(BRANDON, "en-US"), no_controls())

    [paused] = r.events.of(ReadingPaused)
    assert paused == ReadingPaused(1, 2, "episode")  # "Episode 2 is next"
    assert r.events.of(ReadingResumed) == [ReadingResumed(1)]
    assert r.sleeps.count(2.0) < 5  # it went on once the drafts were done, not after the 3-minute cap
    assert [(t.episode, t.text) for t in r.project().turns] == [(1, "Lena waves."), (2, "The kite returns.")]
    assert [(s.number, s.episode) for s in r.project().shots] == [(1, 1), (2, 2)]


async def test_continue_skips_the_wait_for_drafts_and_pause_holds_the_reading_until_continue() -> None:
    r = Reading()
    presses: asyncio.Queue[ReadControl] = asyncio.Queue()

    async def controls() -> AsyncIterator[ReadControl]:
        while True:
            yield await presses.get()

    def press_continue_at_the_episode_break() -> None:
        if r.events.of(ReadingPaused) and not r.events.of(ReadingResumed):
            presses.put_nowait("continue")

    r.on_sleep.append(press_continue_at_the_episode_break)
    await r.run.execute("p1", EPISODES, ReadingOptions(BRANDON, "en-US"), controls())

    assert r.events.of(ReadingResumed) == [ReadingResumed(1)]
    assert len(r.project().turns) == 2  # no drafts were drawn, yet it read on

    # A Pause holds the reading at the next paragraph until Continue.
    r2 = Reading()
    presses2: asyncio.Queue[ReadControl] = asyncio.Queue()
    presses2.put_nowait("pause")

    async def controls2() -> AsyncIterator[ReadControl]:
        while True:
            yield await presses2.get()

    task = asyncio.create_task(r2.run.execute("p1", ROOFTOP, ReadingOptions(BRANDON, "en-US"), controls2()))
    for _ in range(50):
        await asyncio.sleep(0)
        if r2.events.of(ReadingPaused):
            break
    [paused] = r2.events.of(ReadingPaused)
    assert isinstance(paused, ReadingPaused)
    assert paused.reason == "user"
    assert len(r2.voiced()) == paused.next_paragraph < 2  # nothing more is voiced while paused
    presses2.put_nowait("continue")
    await task
    assert r2.events.of(ReadingResumed) == [ReadingResumed(paused.next_paragraph)]
    assert len(r2.voiced()) == 2


async def test_leaving_stops_the_reading_and_keeps_what_was_read() -> None:
    r = Reading()

    async def leave_at_once() -> AsyncIterator[ReadControl]:
        return
        yield "continue"

    ended = await r.run.execute("p1", ROOFTOP, ReadingOptions(BRANDON, "en-US"), leave_at_once())

    assert ended.turns <= 1
    assert len(r.speech.calls) == ended.turns
