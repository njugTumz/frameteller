"""FfmpegVideoRenderer: the MP4 animatic, H.264 + AAC, 1536x1024 at 24 fps (ADR 0011).

One segment per shot between a title card and an end card. Each segment is a still panel with a gentle
zoompan move, cross-faded into the next. A segment is lengthened by the fade, so every shot still starts at
its own time and the voice (cut per shot from the kept narration) stays in sync to the frame.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import itertools
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from frameteller.application.ports import Progress
from frameteller.domain import Animatic, AudioCut, Motion
from frameteller.infrastructure.imaging.text import INK, MUTED, PAPER, font, line_height, wrap

WIDTH, HEIGHT, FPS = 1536, 1024, 24
FADE_FRAMES = 6  # 0.25 s cross-fades
TITLE_MS, END_MS = 1000, 1500
SAMPLE_RATE = 48_000
PRODUCT = "Frameteller"  # the working name (CLAUDE.md): change it here for the end card


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _Segment:
    still: Path
    frames: int  # frames this segment owns on the timeline
    motion: Motion
    caption: Path | None
    audio: tuple[AudioCut, ...]


class FfmpegVideoRenderer:
    def __init__(self, ffmpeg: str = "ffmpeg", timeout_s: float = 900) -> None:
        self._ffmpeg, self._timeout_s = ffmpeg, timeout_s

    async def render(
        self,
        animatic: Animatic,
        frames: Mapping[str, bytes],
        recordings: Mapping[str, bytes],
        *,
        subtitles: bool,
        on_progress: Progress | None = None,
    ) -> bytes:
        with tempfile.TemporaryDirectory(prefix="animatic-") as tmp:
            work = Path(tmp)
            segments, audio_files = await asyncio.to_thread(_prepare, animatic, frames, recordings, subtitles, work)
            args = _command(self._ffmpeg, segments, audio_files, work / "animatic.mp4")
            total_s = sum(s.frames for s in segments) / FPS
            await self._run(args, total_s, on_progress)
            return (work / "animatic.mp4").read_bytes()

    async def _run(self, args: list[str], total_s: float, on_progress: Progress | None) -> None:
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        assert process.stderr is not None

        async def follow() -> None:
            assert process.stdout is not None
            async for raw in process.stdout:
                line = raw.decode(errors="replace").strip()
                if line.startswith("out_time_us=") and on_progress is not None:
                    with contextlib.suppress(ValueError):
                        await on_progress(min(1.0, int(line.split("=", 1)[1]) / 1e6 / total_s))

        stderr = asyncio.ensure_future(process.stderr.read())
        try:
            await asyncio.wait_for(follow(), self._timeout_s)
            code = await asyncio.wait_for(process.wait(), 30)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RenderError("ffmpeg timed out") from None
        errors = (await stderr).decode(errors="replace")
        if code != 0:
            raise RenderError(f"ffmpeg exited with {code}: {errors[-600:]}")


def _prepare(
    animatic: Animatic, frames: Mapping[str, bytes], recordings: Mapping[str, bytes], subtitles: bool, work: Path
) -> tuple[list[_Segment], dict[str, Path]]:
    """Stills, caption overlays and audio files on disk, and every segment's frame count."""
    audio_files = {}
    for i, (key, data) in enumerate(recordings.items()):
        audio_files[key] = work / f"voice{i}.wav"
        audio_files[key].write_bytes(data)

    durations = [TITLE_MS, *(c.duration_ms for c in animatic.clips), END_MS]
    bounds, elapsed = [0], 0
    for ms in durations:  # cumulative rounding: shot starts never drift by more than half a frame
        elapsed += ms
        bounds.append(round(elapsed * FPS / 1000))
    counts = [max(1, b - a) for a, b in itertools.pairwise(bounds)]

    title = work / "title.png"
    _title_card(animatic.title).save(title)
    segments = [_Segment(title, counts[0], Motion.STATIC, None, ())]
    for i, clip in enumerate(animatic.clips):
        still = work / f"shot{i}.png"
        _still(frames[clip.shot_id]).save(still)
        caption = None
        if subtitles and clip.caption.strip():
            caption = work / f"caption{i}.png"
            _caption(clip.caption).save(caption)
        segments.append(_Segment(still, counts[i + 1], clip.motion, caption, clip.audio))
    end = work / "end.png"
    _end_card().save(end)
    segments.append(_Segment(end, counts[-1], Motion.STATIC, None, ()))
    return segments, audio_files


def _command(ffmpeg: str, segments: list[_Segment], audio_files: Mapping[str, Path], out: Path) -> list[str]:
    inputs: list[str] = []
    graph: list[str] = []

    def add_input(*args: str) -> int:
        inputs.extend(args)
        return sum(1 for a in inputs if a == "-i") - 1

    starts, t = [], 0
    for s in segments:
        starts.append(t)
        t += s.frames

    for i, s in enumerate(segments):
        last = i == len(segments) - 1
        length = s.frames + (0 if last else FADE_FRAMES)  # overlap the next segment by the fade
        still = add_input("-i", str(s.still))
        graph.append(f"[{still}:v]{_move(s.motion, length)}[z{i}]")
        video = f"z{i}"
        if s.caption is not None:
            caption = add_input("-i", str(s.caption))
            graph.append(f"[{video}][{caption}:v]overlay=0:0[c{i}]")
            video = f"c{i}"
        graph.append(f"[{video}]format=yuv420p,setsar=1,settb=1/{FPS}[v{i}]")

        seconds = s.frames / FPS
        parts = []
        for j, cut in enumerate(s.audio):
            path = audio_files.get(cut.recording.key)
            if path is None:
                continue
            source = add_input("-i", str(path))
            graph.append(
                f"[{source}:a]atrim=start={cut.start_ms / 1000:.3f}:end={cut.end_ms / 1000:.3f},"
                f"asetpts=PTS-STARTPTS,{_AUDIO_FORMAT}[p{i}_{j}]"
            )
            parts.append(f"[p{i}_{j}]")
        if parts:
            joined = "".join(parts) + (f"concat=n={len(parts)}:v=0:a=1," if len(parts) > 1 else "anull,")
            graph.append(f"{joined}apad,atrim=duration={seconds:.4f},asetpts=PTS-STARTPTS[a{i}]")
        else:
            graph.append(f"anullsrc=r={SAMPLE_RATE}:cl=mono,atrim=duration={seconds:.4f},{_AUDIO_FORMAT}[a{i}]")

    chained = "v0"
    for i in range(1, len(segments)):
        offset = starts[i] / FPS
        graph.append(
            f"[{chained}][v{i}]xfade=transition=fade:duration={FADE_FRAMES / FPS:.4f}:offset={offset:.4f}[x{i}]"
        )
        chained = f"x{i}"
    graph.append("".join(f"[a{i}]" for i in range(len(segments))) + f"concat=n={len(segments)}:v=0:a=1[aout]")

    return [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-nostats",
        "-loglevel",
        "error",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(graph),
        "-map",
        f"[{chained}]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        str(out),
    ]


_AUDIO_FORMAT = f"aresample={SAMPLE_RATE},aformat=sample_fmts=fltp:sample_rates={SAMPLE_RATE}:channel_layouts=mono"


def _move(motion: Motion, frames: int) -> str:
    """zoompan over `frames` output frames. Moving shots are upscaled first so the move does not judder."""
    n = max(1, frames - 1)
    size = f"s={WIDTH}x{HEIGHT}:fps={FPS}:d={frames}"
    if motion is Motion.PUSH_IN:
        return f"scale={WIDTH * 2}:{HEIGHT * 2},zoompan=z='1+0.08*on/{n}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':{size}"
    if motion is Motion.DRIFT:
        return (
            f"scale={WIDTH * 2}:{HEIGHT * 2},"
            f"zoompan=z='1.05':x='(iw-iw/zoom)*(0.25+0.5*on/{n})':y='(ih-ih/zoom)/2':{size}"
        )
    return f"scale={WIDTH}:{HEIGHT},zoompan=z='1':x='0':y='0':{size}"


def _still(data: bytes) -> Image.Image:
    """The panel, cover-fitted to 1536x1024 (panels are 3:2 already, so usually just a resize)."""
    with Image.open(io.BytesIO(data)) as image:
        rgb = image.convert("RGB")
    scale = max(WIDTH / rgb.width, HEIGHT / rgb.height)
    size = (max(WIDTH, round(rgb.width * scale)), max(HEIGHT, round(rgb.height * scale)))
    resized = rgb.resize(size, Image.Resampling.LANCZOS)
    left, top = (size[0] - WIDTH) // 2, (size[1] - HEIGHT) // 2
    return resized.crop((left, top, left + WIDTH, top + HEIGHT))


def _title_card(title: str) -> Image.Image:
    card = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(card)
    lines = wrap(draw, title.strip() or "Untitled story", 84, WIDTH - 320, max_lines=3)
    y = HEIGHT // 2 - len(lines) * line_height(84) // 2 - 30
    for line in lines:
        draw.text((WIDTH // 2, y), line, font=font(84), fill=INK, anchor="mt")
        y += line_height(84)
    draw.text((WIDTH // 2, y + 30), "A storyboard animatic", font=font(36), fill=MUTED, anchor="mt")
    return card


def _end_card() -> Image.Image:
    card = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    ImageDraw.Draw(card).text((WIDTH // 2, HEIGHT // 2), f"Made with {PRODUCT}", font=font(40), fill=MUTED, anchor="mm")
    return card


def _caption(text: str) -> Image.Image:
    """Subtitles: up to two lines in a soft dark band near the bottom, on a transparent overlay."""
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    size = 40
    lines = wrap(draw, text, size, WIDTH - 240, max_lines=2)
    height = len(lines) * line_height(size) + 36
    top = HEIGHT - 60 - height
    widest = max(draw.textlength(line, font=font(size)) for line in lines)
    left = (WIDTH - widest) / 2 - 28
    draw.rounded_rectangle((left, top, WIDTH - left, top + height), radius=14, fill=(20, 18, 16, 170))
    y = top + 18
    for line in lines:
        draw.text((WIDTH // 2, y), line, font=font(size), fill=(255, 255, 255, 255), anchor="mt")
        y += line_height(size)
    return overlay
