"""The real ffmpeg renderer on a tiny timeline. Skipped where ffmpeg is not installed."""

# ruff: noqa: RUF001  (full-width punctuation is the text under test)
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


def caption_band(video: Path, at_s: float, tmp_path: Path) -> int:
    """Brightest pixel in the bottom caption band of the frame at `at_s` (white text lights it up)."""
    still = tmp_path / f"f{at_s}.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{at_s}", "-i", str(video), "-frames:v", "1", str(still)], check=True
    )
    with Image.open(still) as im:
        _, high = im.convert("L").crop((0, 800, 1536, 940)).getextrema()
        assert isinstance(high, int)
        return high


async def test_burned_captions_show_only_while_their_line_is_spoken(tmp_path: Path) -> None:
    clips = (AnimaticClip("s1", 1, MediaRef("a"), 0, 4000, Motion.STATIC),)
    cues = tuple(Cue(1000 + n * 100, 1000 + (n + 1) * 100, f"line {n}") for n in range(10))  # many lines, one stream
    track = CaptionTrack((*cues, Cue(2500, 3500, "The kite drifts over the rooftops.")), "en-US", burn=True)

    video = await FfmpegVideoRenderer().render(
        Animatic("p1", "Kites", clips), {"s1": panel((20, 20, 20))}, {}, captions=track
    )

    out = tmp_path / "a.mp4"
    out.write_bytes(video)
    assert caption_band(out, 3.0, tmp_path) > 200  # the last line, white on the dark band
    assert caption_band(out, 2.3, tmp_path) < 60  # the gap between lines: only the panel
    assert caption_band(out, 4.2, tmp_path) < 60  # after the last line


def ink_rows(still: Image.Image) -> list[tuple[int, int]]:
    """The horizontal bands of a frame that hold text (dark pixels on the paper), top to bottom."""
    grey = still.convert("L")
    pixels = grey.load()
    assert pixels is not None
    rows = [y for y in range(grey.height) if any(int(pixels[x, y]) < 150 for x in range(0, grey.width, 2))]  # type: ignore[arg-type]
    bands: list[tuple[int, int]] = []
    for y in rows:
        if bands and y - bands[-1][1] <= 8:
            bands[-1] = (bands[-1][0], y)
        else:
            bands.append((y, y))
    return bands


def last_second(video: bytes, tmp_path: Path, name: str) -> Image.Image:
    out = tmp_path / f"{name}.mp4"
    out.write_bytes(video)
    still = tmp_path / f"{name}.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-sseof", "-0.5", "-i", str(out), "-frames:v", "1", str(still)], check=True
    )
    with Image.open(still) as im:
        return im.convert("RGB")


@pytest.mark.parametrize(
    ("language", "burn", "invite"),
    [
        ("en-US", True, "Tell your story at frameteller.com"),
        ("en-US", False, "Tell your story at frameteller.com"),
        ("fr-FR", True, "Racontez votre histoire sur frameteller.com"),
        ("pt-BR", True, "Conte sua história em frameteller.com"),
        ("hi-IN", True, "frameteller.com पर अपनी कहानी सुनाइए"),
        ("ar-SA", False, "احكِ قصتك على frameteller.com"),
        ("ja-JP", True, "frameteller.com であなたの物語を語ろう"),
        ("ko-KR", True, "frameteller.com에서 당신의 이야기를 들려주세요"),
        ("zh-CN", True, "在 frameteller.com 讲述你的故事"),
        ("de-DE", True, "Tell your story at frameteller.com"),  # not one of ours: English
    ],
)
async def test_the_last_second_is_a_two_line_end_card_inside_the_safe_area(
    tmp_path: Path, language: str, burn: bool, invite: str
) -> None:
    from frameteller.infrastructure.imaging.ffmpeg_animatic import end_lines

    assert end_lines(language) == ("Made with Frameteller", invite)
    clips = (AnimaticClip("s1", 1, MediaRef("a"), 0, 1000, Motion.STATIC, "Une lanterne."),)
    track = CaptionTrack((Cue(1000, 2000, "Une lanterne."),), language, burn=burn)
    video = await FfmpegVideoRenderer().render(
        Animatic("p1", "Lantern", clips), {"s1": panel((20, 20, 20))}, {}, captions=track
    )
    frame = last_second(video, tmp_path, f"{language}-{burn}")

    bands = ink_rows(frame)
    assert len(bands) == 2, bands  # "Made with Frameteller", then the invitation
    assert all(b - a >= 30 for a, b in bands)  # 64 and 52 px lines: readable at phone size
    box = Image.eval(frame.convert("L"), lambda v: 255 if v < 150 else 0).getbbox()
    assert box is not None
    left, top, right, bottom = box
    assert left >= 1536 * 0.1  # title-safe
    assert right <= 1536 * 0.9
    assert bottom <= 1024 * 0.9
    assert top >= 1024 * 0.1


async def test_a_story_without_captions_ends_on_the_english_card(tmp_path: Path) -> None:
    clips = (AnimaticClip("s1", 1, MediaRef("a"), 0, 800, Motion.STATIC),)
    video = await FfmpegVideoRenderer().render(Animatic("p1", "Quiet", clips), {"s1": panel((20, 20, 20))}, {})
    assert len(ink_rows(last_second(video, tmp_path, "quiet"))) == 2


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("ja-JP", "夜の屋上で、リナは紙の凧を拾った。"),
        ("ko-KR", "밤이 오면 리나는 종이 연을 잡는다."),
        ("zh-CN", "夜幕降临，丽娜接住了一只纸风筝。"),
        ("hi-IN", "छतों पर रात उतरती है, और लीना के हाथों में पतंग आ गिरती है।"),
        ("ar-SA", "يحلّ الليل فوق الأسطح، وتهبط طائرة ورقية بين يدي لينا."),
    ],
)
async def test_captions_in_every_script_are_burned_in_as_drawn(tmp_path: Path, language: str, text: str) -> None:
    from frameteller.infrastructure.imaging.ffmpeg_animatic import _caption

    clips = (AnimaticClip("s1", 1, MediaRef("a"), 0, 2000, Motion.STATIC),)
    track = CaptionTrack((Cue(TITLE_MS + 200, TITLE_MS + 1800, text),), language, burn=True)
    video = await FfmpegVideoRenderer().render(
        Animatic("p1", "Kites", clips), {"s1": panel((20, 20, 20))}, {}, captions=track
    )
    out = tmp_path / "c.mp4"
    out.write_bytes(video)
    still = tmp_path / f"{language}.png"
    at = (TITLE_MS + 1000) / 1000
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{at}", "-i", str(out), "-frames:v", "1", str(still)], check=True
    )
    with Image.open(still) as im:
        frame = im.convert("L")
    expected = Image.new("RGBA", (1536, 1024), (20, 20, 20, 255))
    expected.alpha_composite(_caption(text, language))
    band = (0, 760, 1536, 960)
    want, got = expected.convert("L").crop(band), frame.crop(band)
    _, high = got.getextrema()
    assert isinstance(high, int)
    assert high > 200  # white text on the band
    diff = [abs(a - b) for a, b in zip(want.tobytes(), got.tobytes(), strict=True)]
    assert sum(diff) / len(diff) < 4  # the frame shows the shaped line, glyph for glyph (bar compression)
