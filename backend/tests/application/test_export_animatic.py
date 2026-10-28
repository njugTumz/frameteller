import pytest

from frameteller.application.events import JobUpdated
from frameteller.application.use_cases import ExportAnimatic, GeneratePanel, RequestAnimaticExport
from frameteller.domain import MediaRef, Narration, PanelNotReadyError
from tests.application.conftest import World
from tests.fakes import FakeVideoRenderer, RecordingPublisher

TAKE = MediaRef("projects/p1/narration/t1.wav")


async def drawn(w: World) -> World:
    for shot_id in ("s1", "s2", "s3"):
        await GeneratePanel(w.repo, w.images, w.budget, w.jobs).execute("p1", shot_id, revision=1)
    return w


def export(w: World, renderer: FakeVideoRenderer, events: RecordingPublisher) -> ExportAnimatic:
    return ExportAnimatic(w.repo, w.storage, renderer, events)


async def test_export_renders_every_panel_with_the_kept_voice_and_keeps_the_result(world: World) -> None:
    await drawn(world)
    p = world.project()
    p.keep_narration(Narration("t1", TAKE, 4000))  # builder turns t1..t3 are their own "sessions"
    await world.repo.save(p)
    world.storage.files[TAKE.key] = (b"RIFF-voice", "audio/wav")
    renderer, events = FakeVideoRenderer(), RecordingPublisher()

    result = await export(world, renderer, events).execute("p1", subtitles=True, job_key="k")

    animatic, frames, recordings, subtitles = renderer.rendered[0]
    assert [c.shot_id for c in animatic.clips] == ["s1", "s2", "s3"]
    assert set(frames) == {"s1", "s2", "s3"}
    assert recordings == {TAKE.key: b"RIFF-voice"}
    assert subtitles
    assert (result.duration_ms, result.subtitles, result.voiced) == (12000, True, True)
    assert world.project().animatic == result
    assert world.storage.files[result.video.key][1] == "video/mp4"
    updates = [e for e in events.of(JobUpdated) if isinstance(e, JobUpdated)]
    assert [e.progress for e in updates] == [0.3, 0.6]  # throttled, and never 1: "succeeded" says that
    assert {(e.key, e.status) for e in updates} == {("k", "running")}


async def test_a_new_export_replaces_the_previous_file(world: World) -> None:
    await drawn(world)
    use_case = export(world, FakeVideoRenderer(), RecordingPublisher())
    first = await use_case.execute("p1")
    second = await use_case.execute("p1", subtitles=True)
    assert first.video != second.video
    assert first.video.key not in world.storage.files
    assert not second.voiced


async def test_request_checks_panels_and_dedupes_an_unchanged_storyboard(world: World) -> None:
    with pytest.raises(PanelNotReadyError):
        await RequestAnimaticExport(world.repo, world.jobs).execute("p1")
    await drawn(world)
    request = RequestAnimaticExport(world.repo, world.jobs)

    first = await request.execute("p1")
    again = await request.execute("p1")
    subtitled = await request.execute("p1", subtitles=True)

    assert first.kind == "export_animatic"
    assert first.enqueued
    assert not again.enqueued
    assert subtitled.enqueued
    assert world.jobs.jobs[-1].payload["job_key"] == subtitled.key
