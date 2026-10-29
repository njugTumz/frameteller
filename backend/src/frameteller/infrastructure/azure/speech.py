"""AzureSpeechSynthesizer: Azure AI Speech Text-to-Speech over REST, for "Read it to me" (ADR 0015).

SSML in, `riff-24khz-16bit-mono-pcm` out: the same 24 kHz mono 16-bit PCM as our narration recordings, so the
animatic treats a synthesized narration like a recorded one. No Speech SDK. The key is sent only in the
`Ocp-Apim-Subscription-Key` header and never logged. Speech-to-text stays on Muse Voice Transcribe.
"""

from __future__ import annotations

import io
import json
import wave
from typing import Any
from xml.sax.saxutils import escape, quoteattr

import httpx2

from frameteller.application.errors import InvalidModelOutputError
from frameteller.application.ports import MediaStoragePort, SpokenClip, Voice
from frameteller.domain import MediaRef
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.pricing import TTS_USD_PER_CHARACTER
from frameteller.infrastructure.resilience import ModelCaller, RetryPolicy, Usage

MODEL = "azure-tts"
OUTPUT_FORMAT = "riff-24khz-16bit-mono-pcm"
VOICES_KEY = "system/speech-voices.json"  # the voice list, fetched once (not under projects/: never served raw)


def ssml(text: str, voice: str, language: str) -> str:
    """One voice speaking `text` in `language`; a multilingual voice keeps its own timbre in any language."""
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang={quoteattr(language)}>'
        f"<voice name={quoteattr(voice)}><lang xml:lang={quoteattr(language)}>{escape(text)}</lang></voice></speak>"
    )


def wav_duration_ms(data: bytes) -> int:
    with wave.open(io.BytesIO(data)) as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, 24_000):
            raise ValueError("expected 24 kHz mono 16-bit PCM")
        return int(w.getnframes() * 1000 // w.getframerate())


def _voice(row: dict[str, Any]) -> Voice:
    locale = str(row["Locale"])
    secondary = [str(x) for x in row.get("SecondaryLocaleList") or []]
    return Voice(
        name=str(row["ShortName"]),
        display_name=str(row.get("DisplayName") or row["ShortName"]),
        gender=str(row.get("Gender", "")),
        locale=locale,
        languages=tuple(dict.fromkeys([locale, *secondary])),
    )


class AzureSpeechSynthesizer:
    """SpeechSynthesisPort. Audio is stored at once; only our ref leaves this class."""

    def __init__(
        self,
        http: httpx2.AsyncClient,
        caller: ModelCaller,
        storage: MediaStoragePort,
        settings: Settings,
    ) -> None:
        self._http, self._caller, self._storage = http, caller, storage
        assert settings.azure_speech_key is not None  # checked by the settings validator
        self._key = settings.azure_speech_key
        self._base = settings.azure_speech_tts_base_url.rstrip("/")
        self._policy = RetryPolicy(attempts=settings.retry_attempts, timeout_s=settings.speech_timeout_s)
        self._voices: list[Voice] | None = None

    def _headers(self, **extra: str) -> dict[str, str]:
        return {"Ocp-Apim-Subscription-Key": self._key.get_secret_value(), "User-Agent": "frameteller", **extra}

    async def voices(self) -> list[Voice]:
        if self._voices is not None:
            return self._voices
        ref = MediaRef(VOICES_KEY)
        if await self._storage.exists(ref):
            rows = json.loads(await self._storage.get(ref))
        else:

            async def call() -> tuple[list[dict[str, Any]], Usage]:
                r = await self._http.get(f"{self._base}/cognitiveservices/voices/list", headers=self._headers())
                r.raise_for_status()
                return list(r.json()), Usage(0.0)

            rows = await self._caller.call(MODEL, "voices", call, self._policy)
            await self._storage.put(VOICES_KEY, json.dumps(rows).encode(), "application/json")
        self._voices = [_voice(r) for r in rows if r.get("ShortName") and r.get("Locale")]
        return self._voices

    async def synthesize(self, text: str, voice: str, language: str, store_as: str) -> SpokenClip:
        body = ssml(text, voice, language).encode()

        async def call() -> tuple[bytes, Usage]:
            r = await self._http.post(
                f"{self._base}/cognitiveservices/v1",
                content=body,
                headers=self._headers(
                    **{"Content-Type": "application/ssml+xml", "X-Microsoft-OutputFormat": OUTPUT_FORMAT}
                ),
            )
            r.raise_for_status()
            if not r.content.startswith(b"RIFF"):
                raise InvalidModelOutputError(MODEL, "the answer is not WAV audio")
            return r.content, Usage(round(len(text) * TTS_USD_PER_CHARACTER, 6), input_tokens=len(text))

        data = await self._caller.call(MODEL, "synthesize", call, self._policy)
        try:
            duration = wav_duration_ms(data)
        except (wave.Error, ValueError, EOFError) as e:
            raise InvalidModelOutputError(MODEL, f"unusable audio: {e}") from e
        ref = await self._storage.put(store_as, data, "audio/wav")
        return SpokenClip(ref, duration)
