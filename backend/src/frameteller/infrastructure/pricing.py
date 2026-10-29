"""Model prices in USD from the console (CLAUDE.md section 5). Token prices are per 1M tokens."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenPrice:
    input: float
    cached: float
    output: float

    def cost(self, input_tokens: int | None, output_tokens: int | None, cached_tokens: int | None) -> float:
        i, o, c = input_tokens or 0, output_tokens or 0, cached_tokens or 0
        return ((i - c) * self.input + c * self.cached + o * self.output) / 1_000_000


TOKEN_PRICES = {
    "muse-spark-1.3": TokenPrice(1.25, 0.15, 4.25),
    "muse-spark-1.3-contributor": TokenPrice(0.10, 0.002, 0.20),
    "muse-wonder-1.0": TokenPrice(4.0, 0.20, 20.0),
}
IMAGE_USD = 0.01
SAM_IMAGE_USD = 2.50 / 1000
ASR_USD_PER_HOUR = 0.18
TTS_USD_PER_CHARACTER = 15 / 1_000_000  # Azure AI Speech, neural voices, pay as you go


def token_cost(model: str, input_tokens: int | None, output_tokens: int | None, cached_tokens: int | None) -> float:
    price = TOKEN_PRICES.get(model)
    return price.cost(input_tokens, output_tokens, cached_tokens) if price else 0.0


def asr_cost(audio_ms: int) -> float:
    """Billed per whole second of audio processed."""
    return ASR_USD_PER_HOUR * -(-audio_ms // 1000) / 3600
