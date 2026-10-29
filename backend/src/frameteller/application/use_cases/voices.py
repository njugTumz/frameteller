"""The voices "Read it to me" offers, and a short preview of each (ADR 0015).

A short curated set of multilingual neural voices, US and UK, female and male, so the choice stays simple. Each
lists only the languages it can speak among the ones we offer. Previews are synthesized once per voice and
language and kept, so listening to them costs nothing after the first time.
"""

from __future__ import annotations

from dataclasses import dataclass

from frameteller.application import costs
from frameteller.application.errors import ScriptError
from frameteller.application.ports import BudgetGuard, MediaStoragePort, SpeechSynthesisPort, Voice
from frameteller.domain import MediaRef

DEFAULT_VOICE = "en-US-BrandonMultilingualNeural"
CURATED = (
    DEFAULT_VOICE,
    "en-US-AvaMultilingualNeural",
    "en-US-AndrewMultilingualNeural",
    "en-GB-AdaMultilingualNeural",
    "en-GB-OllieMultilingualNeural",
)
# Language code -> (locale to speak, its own name). English uses the voice's own accent (en-US or en-GB).
LANGUAGES = {
    "en": ("en-US", "English"),
    "fr": ("fr-FR", "Français"),
    "es": ("es-ES", "Español"),
    "hi": ("hi-IN", "हिन्दी"),
    "ar": ("ar-SA", "العربية"),
    "pt": ("pt-BR", "Português"),
}
PREVIEWS = {
    "en": "Night falls over the rooftops, and a paper kite drifts down into Lena's hands.",
    "fr": "La nuit tombe sur les toits, et un cerf-volant en papier descend dans les mains de Lena.",
    "es": "La noche cae sobre los tejados, y una cometa de papel baja hasta las manos de Lena.",
    "hi": "छतों पर रात उतरती है, और एक काग़ज़ की पतंग लीना के हाथों में आ गिरती है।",
    "ar": "يحلّ الليل فوق الأسطح، وتهبط طائرة ورقية بين يدي لينا.",
    "pt": "A noite cai sobre os telhados, e uma pipa de papel desce até as mãos de Lena.",
}
PREVIEW_PROJECT = "voice-previews"  # budget bucket for previews: they belong to no story


@dataclass(frozen=True, slots=True)
class Language:
    code: str  # "fr"
    locale: str  # "fr-FR": what the voice is asked to speak
    name: str  # "Français"


@dataclass(frozen=True, slots=True)
class OfferedVoice:
    name: str
    display_name: str
    gender: str
    accent: str  # "en-US" | "en-GB"
    languages: tuple[Language, ...]


def _languages(voice: Voice) -> tuple[Language, ...]:
    spoken = {loc.lower() for loc in voice.languages}
    offered = []
    for code, (locale, name) in LANGUAGES.items():
        if code == "en":
            offered.append(Language(code, voice.locale, name))  # its own accent
        elif locale.lower() in spoken:
            offered.append(Language(code, locale, name))
    return tuple(offered)


def offered(voices: list[Voice]) -> list[OfferedVoice]:
    """The curated voices this Speech resource has, in our order, each with the languages it speaks."""
    by_name = {v.name: v for v in voices}
    return [
        OfferedVoice(v.name, v.display_name.removesuffix(" Multilingual"), v.gender, v.locale, _languages(v))
        for name in CURATED
        if (v := by_name.get(name))
    ]


class ListVoices:
    def __init__(self, speech: SpeechSynthesisPort) -> None:
        self._speech = speech

    async def execute(self) -> list[OfferedVoice]:
        return offered(await self._speech.voices())

    async def check(self, voice: str, language: str) -> Language:
        """The language a "Read it to me" session asked for, if the voice offers it; else a clear error."""
        for v in await self.execute():
            if v.name == voice:
                for lang in v.languages:
                    if lang.locale.lower() == language.lower() or lang.code == language.lower():
                        return lang
                raise ScriptError(f"{v.display_name} doesn't read that language. Choose another voice or language.")
        raise ScriptError("That voice isn't available. Choose one of the voices offered.")


class PreviewVoice:
    """A sentence in the voice and language, synthesized once and kept."""

    def __init__(self, voices: ListVoices, speech: SpeechSynthesisPort, storage: MediaStoragePort, budget: BudgetGuard):
        self._voices, self._speech, self._storage, self._budget = voices, speech, storage, budget

    async def execute(self, voice: str, language: str) -> bytes:
        lang = await self._voices.check(voice, language)
        key = f"system/voice-previews/{voice}-{lang.locale}.wav"
        if not await self._storage.exists(MediaRef(key)):
            text = PREVIEWS[lang.code]
            await self._budget.charge(PREVIEW_PROJECT, costs.tts(len(text)), f"preview {voice} {lang.locale}")
            await self._speech.synthesize(text, voice, lang.locale, key)
        return await self._storage.get(MediaRef(key))
