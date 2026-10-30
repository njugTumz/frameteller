"""What reaches Muse Image's content filter (ADR 0019).

Production, Oct 30: 7 of 29 image calls were refused, all first tries at a character sheet that said "human
female/man ... average build" next to "full body". A parent telling a story about "my daughter" puts a family
relationship and often an exact age next to the same words. So every prompt is cleaned on its way to the model,
and a refusal gets one plainer try. The user's own words stay as they are in the project and the UI.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace

from frameteller.application.errors import ModelContentFilteredError
from frameteller.application.ports import EditRequest, ImageGenerationPort, ImageRequest, StoredImage

log = logging.getLogger("frameteller.images")

_NUMBERS = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen"
_N = rf"(?:\d{{1,3}}|{'|'.join(_NUMBERS.split())})"
# "6-year-old", "six years old", "aged 6", "age 6", "6 yo", "6yo".
_AGE = re.compile(
    rf"\b(?P<n>{_N})[- ](?:years?|yrs?)[- ]old\b|\b(?:aged?|age) (?P<m>{_N})\b|\b(?P<k>\d{{1,2}}) ?(?:yo|y/o)\b", re.I
)

_KIN = {
    "daughter": "child",
    "son": "child",
    "stepdaughter": "child",
    "stepson": "child",
    "granddaughter": "child",
    "grandson": "child",
    "niece": "child",
    "nephew": "child",
    "kid": "child",
    "baby": "child",
    "daughters": "children",
    "sons": "children",
    "kids": "children",
    "mom": "woman",
    "mum": "woman",
    "mommy": "woman",
    "mummy": "woman",
    "mama": "woman",
    "mother": "woman",
    "stepmother": "woman",
    "aunt": "woman",
    "auntie": "woman",
    "wife": "woman",
    "dad": "man",
    "daddy": "man",
    "papa": "man",
    "father": "man",
    "stepfather": "man",
    "uncle": "man",
    "husband": "man",
    "grandma": "older woman",
    "granny": "older woman",
    "grandmother": "older woman",
    "grandpa": "older man",
    "grandad": "older man",
    "granddad": "older man",
    "grandfather": "older man",
    "sister": "girl",
    "brother": "boy",
    "parents": "grown-ups",
}
_KIN_WORDS = "|".join(sorted(_KIN, key=len, reverse=True))
_POSSESSOR = r"(?:my|our|your|her|his|their|the|a|[A-Z][\w-]*'s)"
_FAMILY = re.compile(
    rf"\b{_POSSESSOR}\s+(?:(?:little|young|baby|big|older|younger|eldest|youngest|only|own)\s+)*(?P<kin>{_KIN_WORDS})\b",
    re.I,
)
# Without a possessive, only the words that make someone a minor in a family ("Wren, my daughter" is caught above).
_CHILD_KIN = re.compile(r"\b(?:step|grand)?(?:daughter|son)s?\b|\bniece\b|\bnephew\b", re.I)

_BUILD_ADJ = (
    "small|slim|slender|average|medium|muscular|stocky|athletic|petite|curvy|heavy|heavyset|large|big|thin|skinny|"
    "tall|short|sturdy|lanky|wiry|chubby|plump|broad|strong|lean|delicate|tiny|compact|solid|normal|regular"
)
_BUILD = re.compile(
    rf"(?P<pre>\b(?:with|of)\s+)?(?:\band\s+)?(?:\ban?\s+)?(?:\b(?:{_BUILD_ADJ}),?\s+){{1,2}}(?:build|frame|physique)\b"
    r"(?P<post>\s+and\b)?",
    re.I,
)
_BODY = [
    re.compile(r"\bfull[- ]body\b", re.I),
    re.compile(r"\b(?:body|figure)\s+(?:shape|type)\b|\bphysique\b", re.I),
    re.compile(r"\b(?:curvy|voluptuous|busty|buxom|skinny|chubby|plump|slender|petite|scrawny)\b", re.I),
]


def _age_word(match: re.Match[str]) -> str:
    raw = (match["n"] or match["m"] or match["k"]).lower()
    years = int(raw) if raw.isdigit() else _NUMBERS.split().index(raw) + 1
    return "young" if years < 13 else "teenage" if years < 18 else "adult"


_YOUNG = re.compile(
    r"\b(?:girl|boy|child|children|kid|kids|toddler|baby|little one|schoolgirl|schoolboy|young|teen\w*|daughter|son|"
    r"niece|nephew)\b",
    re.I,
)
_PEOPLE = re.compile(
    r"\b(?:human|person|people|man|men|woman|women|girl|boy|child|kid|toddler|baby|lady|gentleman|adult|teen\w*|"
    r"daughter|son|mother|father|mom|mum|dad|grand\w+|aunt|uncle|wife|husband|female|male)\b",
    re.I,
)
_GENDER_AGE = re.compile(
    r"\b(?:human|female|male|woman|women|man|men|lady|girl|boy|child|children|kid|kids|toddler|baby|young|"
    r"teen\w*|teenage|adult|little)\b",
    re.I,
)

YOUNG_FRAMING = "storybook illustration of a cheerful young character, fully clothed, friendly standing pose"


def _kin(match: re.Match[str]) -> str:
    word = _KIN[match["kin"].lower()]
    text = f"the {word}"
    return text[0].upper() + text[1:] if match.group(0)[0].isupper() and match.start() == 0 else text


def _tidy(text: str) -> str:
    text = re.sub(r"\b(?i:the|an?)\s+(?=[A-Z]|(?:with|of|and|in|on|wearing)\b|[,.;]|$)", "", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r"[ \t]{2,}", " ", text))
    text = re.sub(r"\s*[,;]\s*(?=[,;])", "", text)
    text = re.sub(r"\b(with|of|and)\s*([,.;])", r"\2", text)
    text = re.sub(r"\b(an?|the)\s+(an?|the)\b", r"\2", text, flags=re.I)
    return re.sub(r"\ba ([aeiou])", r"an \1", text).strip(" ,;")


def sanitize(text: str) -> str:
    """No exact ages, family relationships or body-focused words: "my 6-year-old daughter Wren, small build" ->
    "the young child Wren". Everything else is kept, in order."""
    text = _AGE.sub(_age_word, text)
    text = _FAMILY.sub(_kin, text)
    text = _CHILD_KIN.sub("child", text)
    text = _BUILD.sub(lambda m: " with" if m["pre"] and m["post"] else "", text)
    for body in _BODY:
        text = body.sub("", text)
    text = re.sub(r"\b(young|teenage|adult)\s+\1\b", r"\1", text, flags=re.I)
    return _tidy(text)


def appearance_only(description: str) -> str:
    """The plainer wording for a retry: what they look like, with no age, gender, family or body words at all."""
    text = _GENDER_AGE.sub("", sanitize(description))
    text = re.sub(r"\b(?:the|an?)\s+(?=[,.;]|$)", "", text)
    text = re.sub(r"^\s*(?:with|of|and|,)\s+", "", _tidy(text))
    return _tidy(text)


def is_young(description: str) -> bool:
    return bool(_YOUNG.search(description)) or any(_age_word(m) != "adult" for m in _AGE.finditer(description))


def is_person(description: str) -> bool:
    return bool(_PEOPLE.search(description))


def suggest_description(description: str) -> str:
    """A concrete description to offer after two refusals: storybook wording, the look kept, nothing else."""
    look = appearance_only(description)
    if is_young(description):
        lead = "cheerful young storybook character"
    elif is_person(description):
        lead = "friendly storybook character"
    else:
        return look or "friendly storybook character"
    return f"{lead} with {look}" if look else lead


def suggest_clothes(clothes: str) -> str:
    """For an outfit's sheet: just the clothes, plainly."""
    return appearance_only(clothes) or "simple everyday clothes"


_CHILD_NOUN = re.compile(r"\b(?:girl|boy|child|kid|toddler|baby|schoolgirl|schoolboy)(s)?\b|\bchildren\b", re.I)
_AGE_WORD = re.compile(r"\b(?:young|little|teen|teenage|adult)\s+", re.I)


def plainer(prompt: str) -> str:
    """A generic plainer retry for any prompt (edits): no age words, and a child is just "a character"."""
    text = _CHILD_NOUN.sub(
        lambda m: "characters" if m.group(0).lower() == "children" or m[1] else "character", sanitize(prompt)
    )
    return _tidy(_AGE_WORD.sub("", text))


class SafeImages:
    """ImageGenerationPort that cleans every prompt and retries a refused one once, more plainly.

    The retry uses the request's own `fallback_prompt` when the caller knows a better one (a sheet by look and
    role), otherwise `plainer()`. Refused prompts are not billed, so the one charge the caller made covers it.
    """

    def __init__(self, inner: ImageGenerationPort) -> None:
        self._inner = inner

    async def generate(self, request: ImageRequest, store_as: str) -> StoredImage:
        first = replace(request, prompt=sanitize(request.prompt), fallback_prompt=None)
        try:
            return await self._inner.generate(first, store_as)
        except ModelContentFilteredError:
            log.warning("image refused by the content filter; retrying more plainly", extra={"store_as": store_as})
            retry = sanitize(request.fallback_prompt) if request.fallback_prompt else plainer(request.prompt)
            return await self._inner.generate(replace(first, prompt=retry), store_as)

    async def edit(self, request: EditRequest, store_as: str) -> StoredImage:
        first = replace(request, prompt=sanitize(request.prompt))
        try:
            return await self._inner.edit(first, store_as)
        except ModelContentFilteredError:
            log.warning("image edit refused by the content filter; retrying more plainly", extra={"store_as": store_as})
            return await self._inner.edit(replace(first, prompt=plainer(request.prompt)), store_as)
