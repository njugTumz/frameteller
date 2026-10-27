import pytest

from frameteller.domain import Animatic, CanvasTransform, MediaRef, ObjectMask, PanelNotReadyError, Project
from tests.builders import bitmap, project, shot, turn


def rendered(p: Project) -> Project:
    for s in p.shots:
        p.panel(s.id).record_render(1, MediaRef(f"panels/{s.id}/r1"), f"resp_{s.id}")
    return p


def test_clips_follow_shot_order_and_durations() -> None:
    p = project(shots=0)
    for n, ms in ((1, 3000), (2, 5200), (3, 1800)):
        p.add_turn(turn(n, length=ms))
        p.append_shots([shot(n, "mira", duration_ms=ms)])
    p = rendered(p)
    p.reorder_shots(["s3", "s1", "s2"])
    a = Animatic.from_project(p, MediaRef("audio/take1.wav"))
    assert [(c.shot_id, c.start_ms, c.duration_ms) for c in a.clips] == [
        ("s3", 0, 1800),
        ("s1", 1800, 3000),
        ("s2", 4800, 5200),
    ]
    assert a.duration_ms == 10000
    assert a.narration == MediaRef("audio/take1.wav")


def test_clips_carry_canvas_transforms() -> None:
    p = rendered(project(shots=1))
    panel = p.panel("s1")
    panel.cache_mask(1, ObjectMask("character:mira", "Mira", bitmap(0, 0, 4, 4)))
    panel.transform(CanvasTransform("character:mira", dx=12))
    assert Animatic.from_project(p).clips[0].transforms == (CanvasTransform("character:mira", dx=12),)


def test_every_shot_needs_a_ready_panel() -> None:
    p = project(shots=2)
    p.panel("s1").record_render(1, MediaRef("panels/s1/r1"), "resp")
    with pytest.raises(PanelNotReadyError):
        Animatic.from_project(p)
    p.panel("s2")  # pending panel
    with pytest.raises(PanelNotReadyError):
        Animatic.from_project(p)


def test_empty_project_cannot_be_exported() -> None:
    with pytest.raises(PanelNotReadyError):
        Animatic.from_project(project(shots=0))
