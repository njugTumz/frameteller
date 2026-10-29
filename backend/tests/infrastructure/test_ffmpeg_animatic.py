"""The real ffmpeg renderer on a tiny timeline. Skipped where ffmpeg is not installed."""

import asyncio
import io
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from frameteller.application.audio import wav_bytes
from frameteller.application.ports import CaptionTrack
from frameteller.domain import END_MS, TITLE_MS, Animatic, AnimaticClip, AudioCut, Cue, MediaRef, Motion
from frameteller.infrastructure.imaging.ffmpeg_animatic import FfmpegVideoRenderer

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
TAKE = MediaRef("projects/p1/narration/t1.wav")
TRACK = CaptionTrack((Cue(1000, 1700, "A lighthouse"), Cue(1700, 2200, "at dusk.")), "en-US", burn=True)


def panel(colour: tuple[int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (1920, 1280), colour).save(out, "WEBP")
    return out.getvalue()


def probe(path: Path) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(result.stdout)["streams"]  # type: ignore[no-any-return]


async def test_mp4_is_h264_aac_1536x1024_at_24_fps_with_picture_and_voice_the_same_length(tmp_path: Path) -> None:
    clips = (
        AnimaticClip(
            "s1", 1, MediaRef("a"), 0, 1200, Motion.PUSH_IN, "A lighthouse at dusk.", (AudioCut(TAKE, 0, 1200),)
        ),
        AnimaticClip("s2", 2, MediaRef("b"), 1200, 900, Motion.DRIFT, "", (AudioCut(TAKE, 1500, 2000),)),
        AnimaticClip("s3", 3, MediaRef("c"), 2100, 800, Motion.STATIC),
    )
    frames = {"s1": panel((200, 180, 150)), "s2": panel((150, 180, 200)), "s3": panel((180, 200, 150))}
    voice = wav_bytes(b"\x10\x00" * 24_000 * 3, 24_000)
    seen: list[float] = []

    async def progress(done: float) -> None:
        seen.append(done)

    video = await FfmpegVideoRenderer().render(
        Animatic("p1", "The Lighthouse", clips), frames, {TAKE.key: voice}, captions=TRACK, on_progress=progress
    )

    out = tmp_path / "a.mp4"
    out.write_bytes(video)
    streams = {s["codec_type"]: s for s in probe(out)}
    picture, sound, text = streams["video"], streams["audio"], streams["subtitle"]
    assert (text["codec_name"], text["tags"]["language"]) == ("mov_text", "eng")
    assert (picture["codec_name"], picture["width"], picture["height"]) == ("h264", 1536, 1024)
    assert (picture["pix_fmt"], picture["r_frame_rate"]) == ("yuv420p", "24/1")
    assert sound["codec_name"] == "aac"
    expected = (TITLE_MS + 1200 + 900 + 800 + END_MS) / 1000
    assert float(picture["duration"]) == pytest.approx(expected, abs=0.05)
    assert float(sound["duration"]) == pytest.approx(expected, abs=0.05)
    assert seen
    assert seen[-1] <= 1


async def test_a_broken_frame_fails_with_a_clear_error() -> None:
    clips = (AnimaticClip("s1", 1, MediaRef("a"), 0, 500),)
    with pytest.raises(Exception, match="cannot identify image"):
        await asyncio.wait_for(FfmpegVideoRenderer().render(Animatic("p1", "x", clips), {"s1": b"nope"}, {}), 60)
