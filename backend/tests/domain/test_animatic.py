import pytest

from frameteller.domain import (
    Animatic,
    AudioCut,
    CanvasTransform,
    MediaRef,
    Motion,
    Narration,
    ObjectMask,
    PanelNotReadyError,
    Project,
    Size,
    TranscriptTurn,
)
from frameteller.domain.shots import Framing
from tests.builders import bitmap, project, shot, turn

SIZE = Size(1920, 1280)
TAKE = MediaRef("projects/p1/narration/t1.wav")


def rendered(p: Project) -> Project:
    for s in p.shots:
        p.panel(s.id).record_render(1, MediaRef(f"panels/{s.id}/r1"), f"resp_{s.id}", SIZE)
    return p


def test_clips_follow_shot_order_and_durations() -> None:
    p = project(shots=0)
    for n, ms in ((1, 3000), (2, 5200), (3, 1800)):
        p.add_turn(turn(n, length=ms))
        p.append_shots([shot(n, "mira", duration_ms=ms)])
    p = rendered(p)
    p.reorder_shots(["s3", "s1", "s2"])
    a = Animatic.from_project(p)
    assert [(c.shot_id, c.start_ms, c.duration_ms) for c in a.clips] == [
        ("s3", 0, 1800),
        ("s1", 1800, 3000),
        ("s2", 4800, 5200),
    ]
    assert a.duration_ms == 10000
    assert a.title == "The Lantern Cat"
    assert not a.has_voice  # nothing was kept


def test_clips_show_the_composite_when_objects_were_moved() -> None:
    p = rendered(project(shots=1))
    panel = p.panel("s1")
    panel.cache_mask(1, ObjectMask("character:mira", "Mira", bitmap(0, 0, 4, 4), cutout=MediaRef("cut.png")))
    panel.transform(CanvasTransform("character:mira", dx=12))
    panel.record_composite(1, MediaRef("panels/s1/r1/composites/x.webp"), SIZE)
    assert Animatic.from_project(p).clips[0].image == MediaRef("panels/s1/r1/composites/x.webp")


def test_motion_follows_framing() -> None:
    from dataclasses import replace

    p = project(shots=3)
    p.shots = [
        replace(p.shots[0], framing=Framing.WIDE),
        replace(p.shots[1], framing=Framing.CLOSE_UP),
        replace(p.shots[2], framing=Framing.OVER_SHOULDER),
    ]
    motions = [c.motion for c in Animatic.from_project(rendered(p)).clips]
    assert motions == [Motion.PUSH_IN, Motion.DRIFT, Motion.STATIC]


def test_each_shot_gets_its_own_part_of_the_kept_voice_and_words() -> None:
    p = project(shots=0)
    p.add_turn(TranscriptTurn("t1-b1", "A lighthouse at dusk. Ada climbs the stairs slowly.", 2000, 7000))
    p.add_turn(TranscriptTurn("t1-b2", "Something orange moves.", 8000, 10000))
    p.append_shots(
        [
            shot(1, "mira", turn_ids=("t1-b1",), duration_ms=2000),
            shot(2, "mira", turn_ids=("t1-b1",), duration_ms=3000),
            shot(3, "mira", turn_ids=("t1-b2",), duration_ms=2000),
        ]
    )
    p.keep_narration(Narration("t1", TAKE, 9500))  # the recording stops before the last turn ends
    p = rendered(p)
    p.reorder_shots(["s3", "s1", "s2"])  # the voice moves with its shot

    clips = {c.shot_id: c for c in Animatic.from_project(p).clips}

    assert clips["s1"].audio == (AudioCut(TAKE, 2000, 4000),)
    assert clips["s2"].audio == (AudioCut(TAKE, 4000, 7000),)
    assert clips["s3"].audio == (AudioCut(TAKE, 8000, 9500),)  # clipped to the recording; the rest is silence
    assert clips["s1"].caption == "A lighthouse at dusk."
    assert clips["s2"].caption == "Ada climbs the stairs slowly."
    assert clips["s3"].caption == "Something orange moves."


def test_a_japanese_turn_is_shared_between_its_shots_by_characters() -> None:
    p = project(shots=0)
    p.add_turn(TranscriptTurn("t1-b1", "灯台に夕暮れ。エイダが階段を上る。", 0, 4000))  # no spaces anywhere
    p.append_shots(
        [
            shot(1, "mira", turn_ids=("t1-b1",), duration_ms=1500),
            shot(2, "mira", turn_ids=("t1-b1",), duration_ms=2500),
        ]
    )
    clips = Animatic.from_project(rendered(p)).clips

    assert [c.caption for c in clips] == ["灯台に夕暮れ。", "エイダが階段を上る。"]


def test_a_shot_from_several_turns_gets_all_of_them_and_other_sessions_are_silent() -> None:
    p = project(shots=0)
    p.add_turn(TranscriptTurn("t1-b1", "Night.", 0, 1000))
    p.add_turn(TranscriptTurn("t1-b2", "Rain.", 1500, 2500))
    p.add_turn(TranscriptTurn("t2-b1", "Later.", 0, 1000))
    p.append_shots(
        [
            shot(1, "mira", turn_ids=("t1-b1", "t1-b2"), duration_ms=2000),
            shot(2, "mira", turn_ids=("t2-b1",), duration_ms=1000),
        ]
    )
    p.keep_narration(Narration("t1", TAKE, 5000))
    clips = Animatic.from_project(rendered(p)).clips

    assert clips[0].audio == (AudioCut(TAKE, 0, 1000), AudioCut(TAKE, 1500, 2500))
    assert clips[0].caption == "Night. Rain."
    assert clips[1].audio == ()
    assert clips[1].caption == "Later."


def test_every_shot_needs_a_ready_panel() -> None:
    p = project(shots=2)
    p.panel("s1").record_render(1, MediaRef("panels/s1/r1"), "resp", SIZE)
    with pytest.raises(PanelNotReadyError):
        Animatic.from_project(p)
    p.panel("s2")  # pending panel
    with pytest.raises(PanelNotReadyError):
        Animatic.from_project(p)


def test_empty_project_cannot_be_exported() -> None:
    with pytest.raises(PanelNotReadyError):
        Animatic.from_project(project(shots=0))
