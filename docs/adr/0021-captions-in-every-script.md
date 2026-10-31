# ADR 0021: Captions and cards in every script we speak

- **Status:** Accepted
- **Date:** 2026-10-31
- **Deciders:** Isaac Tumuti
- **Builds on:** [ADR 0011](0011-animatic-export.md) (the animatic), [ADR 0015](0015-script-mode.md) (Read it to me)

## Context

v1.2.0 adds Japanese, Korean and Mandarin Chinese to the six languages we already had. Before this, only Latin-script
captions were burned in, because Pillow's bundled font draws Latin only. Hindi and Arabic got a soft track and an .srt
file, and their end cards fell back to English. Japanese and Chinese also put no spaces between words, while captions,
turn sharing between shots and the teleprompter all counted words with `str.split()`.

## Decision

- **Text units live in the domain (`domain/text.py`).** A text is split into words, except kana and Han, where each
  character is a unit with its punctuation attached. Tokens are joined back with a space only where the script uses
  one. Caption lines, time shares, turn sharing, the live transcript and teleprompter cuts all use these units.
- **CJK captions split by characters.** Text of up to 18 characters stays one line. Longer text splits evenly, and a
  line ends after a comma or full stop in its second half. Korean keeps whole words.
- **The teleprompter matches Japanese and Chinese character by character**, with an 8-character tail instead of
  5 words.
- **We draw captions ourselves with Pillow, not libass.** That is how the renderer already worked: caption images go
  through one ffmpeg overlay. A line is cut into runs, one per font. Pillow's font draws Latin, and bundled Noto
  fonts (OFL, `infrastructure/imaging/fonts/`) draw the rest. Each run is shaped by raqm (HarfBuzz and FriBidi, both
  in the image). A line that starts in Arabic is laid out right to left.
- **The CJK fonts are the per-language subset OTFs (JP, KR, SC, about 4.5 to 8 MB each)**, not the full CJK
  collection. The image grew by 33 MB uncompressed (15 MB compressed).
- **The end card's invitation comes from a fixed table in nine languages**, with a `{site}` placeholder because the
  URL's position changes with word order. The table is never a model's translation.
- **The narrator may choose their speaking language** (default auto-detect). It is sent to Muse Voice Transcribe as
  `languageBias: ["ja-JP"]`, which must be a list, and kept with the recording. Without a kept language, the
  captions' language comes from the transcript's script.

## Consequences

- Every caption language we offer is burned in. Languages outside the nine still narrate through auto-detect and
  keep a soft track.
- Line breaking does no dictionary-based word segmentation. A Japanese or Chinese line may end mid-word when no
  comma is near.
- The end-card translations are ours; a native speaker should check them before a wider launch.
