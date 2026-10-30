"""Remove a beat said by mistake, merge two beats, delete a shot: the story, the timing and the animatic follow."""

from dataclasses import replace

import pytest

from frameteller.domain import (
    Animatic,
    InvalidValueError,
    MediaRef,
    Narration,
    Project,
    TranscriptTurn,
    UnknownTurnError,
)
from tests.builders import MIRA, shot
from tests.fakes import PANEL_SIZE

REC = MediaRef("projects/p1/narration/rec.wav")


def told(*texts: str, shots_per_turn: tuple[int, ...] = ()) -> Project:
    """A recorded story: one beat per text (4 s each, back to back, session "rec"), shots drawn and ready."""
    p = Project(id="p1")
    p.upsert_character(MIRA)
    p.bible.set_reference("mira", MediaRef("refs/mira.webp"))
    p.bible.approve()
    shots, n = [], 1
    for i, text in enumerate(texts):
        t = TranscriptTurn(f"rec-{i}", text, i * 4000, (i + 1) * 4000)
        p.add_turn(t)
        count = shots_per_turn[i] if i < len(shots_per_turn) else 1
        for _ in range(count):
            shots.append(shot(n, "mira", turn_ids=(t.id,), duration_ms=4000 // count))
            n += 1
    p.append_shots(shots)
    for s in p.shots:
        p.panel(s.id).record_render(1, MediaRef(f"panels/{s.id}.webp"), f"resp_{s.id}", PANEL_SIZE)
    p.keep_narration(Narration("rec", REC, 4000 * len(texts)))
    return p


def voice(a: Animatic) -> list[tuple[int, str, list[tuple[int, int]]]]:
    return [(c.number, c.caption, [(cut.start_ms, cut.end_ms) for cut in c.audio]) for c in a.clips]


def test_removing_a_beat_said_by_mistake_takes_its_shot_words_and_voice_out() -> None:
    p = told("Wren wakes up early.", "period", "She runs to the window.")
    assert p.remove_turn("rec-1") == ["s2"]
    assert [t.text for t in p.turns] == ["Wren wakes up early.", "She runs to the window."]
    assert [(s.id, s.number) for s in p.shots] == [("s1", 1), ("s3", 2)]
    assert "s2" not in p.panels
    assert voice(Animatic.from_project(p)) == [
        (1, "Wren wakes up early.", [(0, 4000)]),
        (2, "She runs to the window.", [(8000, 12000)]),  # the stretch of "period" (4-8 s) is never played
    ]
    assert Animatic.from_project(p).duration_ms == 8000
    with pytest.raises(UnknownTurnError):
        p.remove_turn("rec-1")


def test_a_shot_made_from_two_beats_keeps_the_other_one() -> None:
    p = told("Wren wakes up early.", "She runs to the window.")
    p.shots[0] = replace(p.shots[0], source_turn_ids=("rec-0", "rec-1"), duration_ms=8000)
    p.shots = [p.shots[0]]
    p.panels.pop("s2")
    p.remove_turn("rec-1")
    assert p.shots[0].source_turn_ids == ("rec-0",)
    assert p.shots[0].duration_ms == 4000


def test_merging_two_beats_joins_their_words_and_reshares_the_time() -> None:
    p = told("Wren runs down the", "stairs and spins around to show her dad.")
    merged = p.merge_turns("rec-0", "rec-1")
    assert (merged.id, merged.text, merged.start_ms, merged.end_ms) == (
        "rec-0",
        "Wren runs down the stairs and spins around to show her dad.",
        0,
        8000,
    )
    assert [t.id for t in p.turns] == ["rec-0"]
    assert [s.source_turn_ids for s in p.shots] == [("rec-0",), ("rec-0",)]
    assert sum(s.duration_ms for s in p.shots) == 8000
    clips = Animatic.from_project(p).clips
    assert " ".join(c.caption for c in clips) == merged.text
    assert [(cut.start_ms, cut.end_ms) for c in clips for cut in c.audio] == [(0, 4000), (4000, 8000)]


def test_only_neighbouring_beats_of_one_recording_merge() -> None:
    p = told("one", "two", "three")
    with pytest.raises(InvalidValueError, match="right after"):
        p.merge_turns("rec-0", "rec-2")
    p.turns[2] = replace(p.turns[2], id="other-2")
    p.shots[2] = replace(p.shots[2], source_turn_ids=("other-2",))
    with pytest.raises(InvalidValueError, match="same recording"):
        p.merge_turns("rec-1", "other-2")


def test_deleting_one_of_a_beats_shots_skips_its_voice_and_words() -> None:
    p = told("Wren puts on her costume and looks in the mirror", shots_per_turn=(2,))
    p.delete_shot("s1")
    assert [(s.id, s.number, s.voice_from_ms) for s in p.shots] == [("s2", 1, 2000)]
    assert voice(Animatic.from_project(p)) == [(1, "and looks in the mirror", [(2000, 4000)])]


def test_deleting_the_last_shot_of_a_beat_keeps_the_first_shots_words() -> None:
    p = told("Wren puts on her costume and looks in the mirror", "She grins.", shots_per_turn=(2, 1))
    p.delete_shot("s2")
    assert [(s.id, s.number) for s in p.shots] == [("s1", 1), ("s3", 2)]
    assert voice(Animatic.from_project(p)) == [
        (1, "Wren puts on her costume", [(0, 2000)]),
        (2, "She grins.", [(4000, 8000)]),
    ]
    assert next(t.text for t in p.turns).endswith("mirror")  # the words stay in the transcript


def test_merging_again_resets_the_voice_of_shots_whose_sibling_was_deleted() -> None:
    p = told("Wren puts on her costume and looks in the mirror", "She grins.", shots_per_turn=(2, 1))
    p.delete_shot("s1")
    p.merge_turns("rec-0", "rec-1")
    assert all(s.voice_from_ms is None for s in p.shots)
    assert sum(s.duration_ms for s in p.shots) == 8000
