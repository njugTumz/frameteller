"""Audio formats the application produces: our own PCM as WAV, for the kept narration."""

from __future__ import annotations

import struct

SAMPLE_RATE = 24_000  # what live sessions receive (docs/api-events.md)
BYTES_PER_MS = 48


def wav_bytes(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    """A canonical 44-byte-header WAV around mono 16-bit little-endian PCM."""
    pcm = pcm[: len(pcm) - len(pcm) % 2]
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        1,  # mono
        rate,
        rate * 2,
        2,
        16,
        b"data",
        len(pcm),
    )
    return header + pcm
