"""AzureSpeechSynthesizer against Azure's REST API: recorded voices and audio (tests/fixtures/record_speech.py)."""

import io
import json
import wave
from pathlib import Path
from xml.etree import ElementTree

import httpx2
import pytest
from pydantic import SecretStr

from frameteller.application.audio import wav_bytes
from frameteller.application.errors import (
    InvalidModelOutputError,
    ModelRateLimitedError,
    ModelRejectedError,
)
from frameteller.application.ports import SpokenClip
from frameteller.application.use_cases.voices import CURATED, offered
from frameteller.domain import MediaRef
from frameteller.infrastructure.azure.speech import VOICES_KEY, AzureSpeechSynthesizer, ssml, wav_duration_ms
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.local import LocalFileMediaStorage
from frameteller.infrastructure.resilience import ModelCaller
from tests.fakes import InMemorySpendLedger

AZURE = Path(__file__).parent.parent / "fixtures" / "azure"
FAKE_SPEECH_KEY = "speech-test-not-a-real-key-0000"
recorded = pytest.mark.skipif(
    not (AZURE / "voices_list.json").exists(), reason="record with tests/fixtures/record_speech.py"
)


@pytest.fixture
def speech_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"azure_speech_key": SecretStr(FAKE_SPEECH_KEY)})


def synthesizer(
    handler: httpx2.MockTransport, caller: ModelCaller, storage: LocalFileMediaStorage, settings: Settings
) -> AzureSpeechSynthesizer:
    return AzureSpeechSynthesizer(httpx2.AsyncClient(transport=handler), caller, storage, settings)


def silence_wav(ms: int) -> bytes:
    return wav_bytes(b"\x00\x00" * 24 * ms)


async def test_synthesis_sends_ssml_with_the_key_header_and_stores_24khz_wav(
    caller: ModelCaller, storage: LocalFileMediaStorage, speech_settings: Settings, ledger: InMemorySpendLedger
) -> None:
    seen: list[httpx2.Request] = []

    def answer(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, content=silence_wav(1250), headers={"content-type": "audio/x-wav"})

    tts = synthesizer(httpx2.MockTransport(answer), caller, storage, speech_settings)
    clip = await tts.synthesize("Lena & the <kite>.", "en-US-BrandonMultilingualNeural", "fr-FR", "projects/p1/s.wav")

    [request] = seen
    assert str(request.url) == "https://eastus2.tts.speech.microsoft.com/cognitiveservices/v1"
    assert request.headers["Ocp-Apim-Subscription-Key"] == FAKE_SPEECH_KEY
    assert request.headers["X-Microsoft-OutputFormat"] == "riff-24khz-16bit-mono-pcm"
    assert request.headers["Content-Type"] == "application/ssml+xml"
    root = ElementTree.fromstring(request.content)  # well-formed: the text is escaped
    voice = root.find("{http://www.w3.org/2001/10/synthesis}voice")
    assert voice is not None
    assert voice.get("name") == "en-US-BrandonMultilingualNeural"
    lang = voice.find("{http://www.w3.org/2001/10/synthesis}lang")
    assert lang is not None
    assert lang.get("{http://www.w3.org/XML/1998/namespace}lang") == "fr-FR"
    assert lang.text == "Lena & the <kite>."
    assert clip == SpokenClip(MediaRef("projects/p1/s.wav"), 1250)
    assert await storage.get(clip.ref) == silence_wav(1250)
    [usage] = ledger.usage
    assert usage.model == "azure-tts"
    assert usage.cost_usd == pytest.approx(18 * 15 / 1_000_000)


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, ModelRejectedError), (400, ModelRejectedError), (429, ModelRateLimitedError)],
)
async def test_failures_map_to_model_errors(
    caller: ModelCaller, storage: LocalFileMediaStorage, speech_settings: Settings, status: int, error: type
) -> None:
    tts = synthesizer(httpx2.MockTransport(lambda _: httpx2.Response(status)), caller, storage, speech_settings)
    with pytest.raises(error):
        await tts.synthesize("Hello.", "en-US-BrandonMultilingualNeural", "en-US", "projects/p1/s.wav")


async def test_an_answer_that_is_not_24khz_mono_wav_is_refused(
    caller: ModelCaller, storage: LocalFileMediaStorage, speech_settings: Settings
) -> None:
    for content in (b"<html>busy</html>", wav_bytes(b"\x00\x00" * 160, rate=16_000)):

        def answer(_: httpx2.Request, body: bytes = content) -> httpx2.Response:
            return httpx2.Response(200, content=body)

        tts = synthesizer(httpx2.MockTransport(answer), caller, storage, speech_settings)
        with pytest.raises(InvalidModelOutputError):
            await tts.synthesize("Hello.", "en-US-BrandonMultilingualNeural", "en-US", "projects/p1/s.wav")


def test_ssml_escapes_quotes_in_attributes() -> None:
    assert ElementTree.fromstring(ssml('Say "hi".', 'a"b', "en-US")) is not None


@recorded
async def test_the_recorded_voice_list_offers_the_curated_voices_and_is_fetched_once(
    caller: ModelCaller, storage: LocalFileMediaStorage, speech_settings: Settings
) -> None:
    body = (AZURE / "voices_list.json").read_bytes()
    calls: list[str] = []

    def answer(request: httpx2.Request) -> httpx2.Response:
        calls.append(str(request.url))
        return httpx2.Response(200, content=body, headers={"content-type": "application/json"})

    tts = synthesizer(httpx2.MockTransport(answer), caller, storage, speech_settings)
    voices = await tts.voices()
    again = await synthesizer(httpx2.MockTransport(answer), caller, storage, speech_settings).voices()

    assert calls == ["https://eastus2.tts.speech.microsoft.com/cognitiveservices/voices/list"]
    assert again == voices  # the second instance reads the cached list from storage
    assert await storage.exists(MediaRef(VOICES_KEY))
    curated = offered(voices)
    assert [v.name for v in curated] == list(CURATED)
    assert [v.display_name for v in curated] == ["Brandon", "Ava", "Andrew", "Ada", "Ollie"]  # not "Ada Multilingual"
    assert {v.accent for v in curated} == {"en-US", "en-GB"}
    assert {v.gender for v in curated} == {"Male", "Female"}
    for v in curated:
        # Every curated voice reads all six languages we offer.
        assert [x.code for x in v.languages] == ["en", "fr", "es", "hi", "ar", "pt"], v.name


@recorded
async def test_recorded_french_speech_is_24khz_mono_16bit(
    caller: ModelCaller, storage: LocalFileMediaStorage, speech_settings: Settings
) -> None:
    meta = json.loads((AZURE / "synthesize_fr.json").read_text())
    audio = (AZURE / "synthesize_fr.wav").read_bytes()
    assert (meta["channels"], meta["sample_width"], meta["rate"]) == (1, 2, 24_000)
    assert meta["content_type"].startswith("audio/")
    assert 500 < meta["full_duration_ms"] < 10_000

    tts = synthesizer(
        httpx2.MockTransport(
            lambda _: httpx2.Response(200, content=audio, headers={"content-type": meta["content_type"]})
        ),
        caller,
        storage,
        speech_settings,
    )
    clip = await tts.synthesize(meta["text"], meta["voice"], "fr-FR", "projects/p1/fr.wav")
    assert clip.duration_ms == wav_duration_ms(audio) == 500
    with wave.open(io.BytesIO(await storage.get(clip.ref))) as w:
        assert w.getframerate() == 24_000
