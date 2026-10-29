"""Model prices in USD (CLAUDE.md section 5). Used for budget reservations."""

IMAGE = 0.01
SAM_IMAGE = 2.50 / 1000
# One supervisor review: reserved at a Spark review's price (a panel and up to three sheets at 768 px, low
# reasoning; see docs/supervisor-eval.md), whichever reviewer serves it. Glimmer's GPU time is billed by Modal.
REVIEW = 0.006
# Translating an animatic's captions with Spark: a few hundred tokens each way, reserved generously.
TRANSLATION = 0.003
TTS_PER_CHARACTER = 15 / 1_000_000  # Azure neural Text-to-Speech


def tts(characters: int) -> float:
    return round(characters * TTS_PER_CHARACTER, 6)
