# ADR 0011: Animatic export with the narrator's own voice

- **Status:** Accepted
- **Date:** 2026-10-28
- **Deciders:** Isaac Tumuti

## Context

The P0 promise is "I talked for 60 seconds and got a timed animatic". Shots already carry their time:
- A beat's shots share the beat's spoken stretch.
- Leading silence is trimmed ([ADR 0008](0008-reliable-beats.md)).

The narration is kept as a WAV only when the narrator agrees (`keep_audio`). Shots can be reordered, corrected or revealed later, so the voice has to follow the shot, not the clock of the recording.

## Decision

- **Timeline.** There is one clip per shot, in storyboard order, lasting the shot's `duration_ms`. A 1 s title card comes first and a 1.5 s "Made with Frameteller" card comes last.
- **Voice per shot.** A shot's audio is the part of its turn's recording it took its time from:
  - The shots of one turn share it in spoken order.
  - A shot built from several turns gets all of them back to back.
  - The audio is cut, padded or trimmed to the clip's length, so a reordered storyboard keeps every line on its own picture.
  - Shots from a session whose audio was not kept are silent.
- **Captions.** Optional burned-in subtitles show the words of the shot's part of the turn. The words are split in proportion to the shot's time, like the audio.
- **Picture.** Each panel shows as it appears in the storyboard, including its composite ([ADR 0010](0010-clean-plates.md)). It is resized to 1536x1024, with a gentle move chosen by framing:
  - Wide shots get a slow push-in (8%).
  - Close-ups drift slightly.
  - Other framings stay static.
  - Clips cross-fade over 0.25 s. Each clip but the last is lengthened by the fade, so every shot still starts at its own time.
  - Frame boundaries are rounded cumulatively, so starts never drift by more than half a frame.
- **Encoding.** ffmpeg (`FfmpegVideoRenderer`, behind `VideoRendererPort`) encodes in one pass:
  - Video: H.264, `-preset veryfast -crf 23`, yuv420p, 24 fps.
  - Audio: AAC at 48 kHz mono.
  - `+faststart`, so playback starts before the download ends.
- **Job.** The export runs as an `export_animatic` job:
  - Its key is a digest of the timeline and options, so an unchanged storyboard renders once.
  - ffmpeg's `-progress` output is published as `job.updated` with `progress` (0–1) every 5%.
  - The project keeps only the latest export; the previous file is deleted.
- **Serving.** `/media` answers single byte ranges, so the browser player can seek, and `?download=1` sets `Content-Disposition`.

## Consequences

- The animatic needs no model call: export is free in Meta credits and costs only CPU.
- Picture and voice are the same length by construction: the tests check both streams with ffprobe.
- Exports run on the single backend replica ([ADR 0009](0009-single-backend-replica.md)). A minute of animatic takes seconds of CPU; a 900 s timeout guards against a stuck ffmpeg.
- Turn timestamps are turn-level, not word-level (CLAUDE.md §5). When one turn yields several shots, the cut between them falls by time share, so it can land mid-word. Beats keep this rare.
