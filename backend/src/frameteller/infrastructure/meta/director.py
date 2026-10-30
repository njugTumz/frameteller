"""MetaSparkDirectorAdapter: transcript turns -> shots with Spark structured output (ADR 0002)."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

from frameteller.application.errors import InvalidModelOutputError
from frameteller.application.ports import DirectedTurn, EditIntent, LookChange, ShotDraft, ShotRevision
from frameteller.application.use_cases.direct_turn import REVEAL_WINDOW
from frameteller.domain import EVERYDAY, Character, Framing, InvalidValueError, Project, Shot, TranscriptTurn
from frameteller.infrastructure.config import Effort, Settings
from frameteller.infrastructure.pricing import token_cost
from frameteller.infrastructure.resilience import ModelCaller, RetryPolicy, Usage

# Stable prefix part 1: identical bytes on every request so prompt caching can hit.
SYSTEM_PROMPT = """You are the director's assistant in Frameteller, a tool that turns a spoken story into a storyboard.

You receive the character bible, the shots so far, and transcript turns as JSON.
Each turn has an id, start_ms, end_ms and text.

Return:
- new_characters: characters that appear in the turns but are not in the bible yet, including animals.
  id is a short lowercase slug (e.g. "mira"). canonical_description is ONE stable visual description used
  to draw the character in every panel: species, age group (child, teenager, adult or older adult; never an
  exact age, never a family relationship such as "my daughter"), height, face, hair or fur, and distinctive
  features; never body shape. A child the narrator calls "my daughter" or "my son" is "a young girl" or
  "a young boy". Describe clothing and accessories only when the transcript mentions them; animals wear
  nothing unless the transcript says so. Be concrete. Never mention framing or actions. Never contradict the transcript.
- shots: one or more shots per turn, in story order.
  framing is one of wide, medium, close_up, over_shoulder, insert. Honour explicit cues such as "wide shot"
  or "close on". A turn from a written script may start with a scene heading ("Scene: EXT. ROOFTOP - NIGHT."):
  use it for the setting, and never draw it as text. A turn that says '<Name> says: "..."' is dialogue.
  character_ids lists only characters visible in the shot, from the bible or new_characters.
  setting is where and when, action is what we see, dialogue is the spoken words or "" if none.
  source_turn_ids lists the turn ids the shot comes from.
A turn with no story content (hesitation, a correction to the operator) may produce no shots.
Never invent a character, name or species the narration does not state. Something described vaguely
("something small and orange") is not a character yet: keep it vague in the action, with no character for it.
- updated_shots: when this turn reveals who or what an earlier vague or wrongly guessed thing was, revise
  those of the last 3 shots so far: their number, their full character_ids and their action rewritten with
  the reveal. Return [] when nothing is revealed. Never revise older shots.
- outfit_changes: when a turn says a character puts on a costume or changes clothes, record it so every later
  panel keeps it: character_id; look_id, a short lowercase slug for the outfit (e.g. "farmer_costume"), or
  "everyday" when they change back into the clothes of their canonical description; label, two or three words
  (e.g. "Farmer costume"); clothes, only what they now wear, concretely (garments, colours, shoes, accessories);
  from_shot, the number of the first shot that shows the new clothes: one of this turn's new shots (numbered on
  from the shots so far) or, when the turn reveals a change that already happened, one of the last 3 shots so
  far. They keep wearing it until another change. To change back into a look the bible already lists for them,
  reuse its look_id. A character's canonical_description describes what they wear when we first meet them. Return
  [] when nobody changes clothes.
- refusal: "" normally. Stories must be original. When a turn names a real, identifiable person (a public
  figure, a celebrity, a politician) or a well-known copyrighted character (from films, TV, comics, games or
  books), create no character and no shot for them, and set refusal to one short, friendly sentence asking
  the narrator to describe an original character instead, e.g. "Let's keep the cast original: describe your
  own character instead of a famous one." Other shots in the turn are made as usual.
Never add real people, brands or copyrighted characters yourself."""

CHARACTERS_PROMPT = """You maintain the character bible for a storyboard.
List every character in the transcript, including animals, that is not already in the bible.
id is a short lowercase slug. canonical_description is one concrete, stable visual description:
species, age group (child, teenager, adult or older adult; never an exact age or a family relationship), height,
face, hair or fur, and distinctive features; never body shape. Describe clothing and accessories only
when the transcript mentions them; animals wear nothing unless the transcript says so."""


EDIT_PROMPT = """You route a storyboard artist's edit instruction for one panel into an appearance edit.
Return:
- target: the object to change, as a short noun phrase that identifies it in the picture,
  using the character bible when it is a character (e.g. "girl in the yellow raincoat").
- parts: every visible part of the target the change must reach, so none is left behind
  (e.g. a coat colour change names "raincoat", "hood" and "sleeves"). At most 8.
- change: the appearance change as a short imperative (e.g. "make it red").
Appearance only: colour, clothing, material, expression, lighting. Never invent story content."""


class CharacterOut(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    name: str = Field(min_length=1)
    canonical_description: str = Field(min_length=1)


class ShotOut(BaseModel):
    framing: Literal["wide", "medium", "close_up", "over_shoulder", "insert"]
    character_ids: list[str]
    setting: str
    action: str
    dialogue: str
    source_turn_ids: list[str] = Field(min_length=1)


class UpdatedShotOut(BaseModel):
    number: int = Field(ge=1)
    character_ids: list[str]
    action: str = Field(min_length=1)


class OutfitChangeOut(BaseModel):
    character_id: str
    look_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    label: str = Field(max_length=40)
    clothes: str = Field(max_length=400)
    from_shot: int = Field(ge=1)


class DirectorOutput(BaseModel):
    new_characters: list[CharacterOut]
    shots: list[ShotOut]
    updated_shots: list[UpdatedShotOut] = Field(default_factory=list, max_length=3)
    outfit_changes: list[OutfitChangeOut] = Field(default_factory=list, max_length=8)
    refusal: str = Field(default="", max_length=300)


class CharactersOutput(BaseModel):
    characters: list[CharacterOut]


TRANSLATE_PROMPT = """You translate the narration of an original, family-friendly story for a voice to read aloud.
Translate each text into the requested language, keeping its meaning, tone and every name exactly. Write numbers
and units as a narrator would say them. Return the translations in the same order, one per text, nothing else."""


class TranslationOutput(BaseModel):
    translations: list[str] = Field(max_length=40)


class EditOutput(BaseModel):
    target: str = Field(min_length=1, max_length=120)
    parts: list[str] = Field(max_length=8)
    change: str = Field(min_length=1, max_length=200)


class MetaSparkDirectorAdapter:
    """DirectorPort on Chat Completions with Pydantic structured output and one validation retry."""

    def __init__(self, client: AsyncOpenAI, caller: ModelCaller, settings: Settings) -> None:
        self._client, self._caller, self._settings = client, caller, settings
        self._policy = RetryPolicy(attempts=settings.retry_attempts, timeout_s=settings.text_timeout_s)

    async def direct_turn(self, turn: TranscriptTurn, project: Project) -> DirectedTurn:
        out = await self._direct(project, [turn], self._settings.director_effort_turn, "direct_turn")
        return self._to_port(out, project, [turn])

    async def direct_story(self, project: Project) -> DirectedTurn:
        out = await self._direct(project, project.turns, self._settings.director_effort_story, "direct_story")
        return self._to_port(out, project, project.turns)

    async def extract_characters(self, turns: Sequence[TranscriptTurn], known: Sequence[Character]) -> list[Character]:
        messages = [
            {"role": "system", "content": CHARACTERS_PROMPT},
            {"role": "system", "content": _bible_message(known)},
            {"role": "user", "content": "Transcript turns:\n" + _turns_json(turns)},
        ]
        out = await self._parse(messages, CharactersOutput, self._settings.director_effort_story, "characters", None)
        known_ids = {c.id for c in known}
        return [_character(c) for c in out.characters if c.id not in known_ids]

    async def translate(self, texts: Sequence[str], language: str) -> list[str]:
        """TranslatorPort: the narration only; shots are directed from the original (ADR 0015)."""
        if not texts:
            return []
        messages = [
            {"role": "system", "content": TRANSLATE_PROMPT},
            {
                "role": "user",
                "content": f"Language: {language}\nTexts:\n" + json.dumps(list(texts), ensure_ascii=False),
            },
        ]

        def check(out: TranslationOutput) -> list[str]:
            if len(out.translations) != len(texts):
                return [f"translations: expected {len(texts)} items, one per text, got {len(out.translations)}"]
            return [f"translation {n} is empty" for n, t in enumerate(out.translations, 1) if not t.strip()]

        effort = self._settings.director_effort_turn
        out = await self._parse(messages, TranslationOutput, effort, "translate", check)
        return [t.strip() for t in out.translations]

    async def interpret_edit(self, instruction: str, shot: Shot, cast: Sequence[Character]) -> EditIntent:
        shot_json = json.dumps(
            {"framing": shot.framing.value, "setting": shot.setting, "action": shot.action}, ensure_ascii=False
        )
        messages = [
            {"role": "system", "content": EDIT_PROMPT},
            {"role": "system", "content": _bible_message(cast)},
            {"role": "user", "content": f"Shot: {shot_json}\nInstruction: {instruction}"},
        ]
        out = await self._parse(messages, EditOutput, self._settings.director_effort_turn, "interpret_edit", None)
        parts = tuple(dict.fromkeys(p.strip() for p in out.parts if p.strip()))
        return EditIntent(out.target.strip(), parts, out.change.strip())

    async def _direct(
        self, project: Project, turns: Sequence[TranscriptTurn], effort: Effort, operation: str
    ) -> DirectorOutput:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": _bible_message(list(project.bible.characters.values()))},
            {
                "role": "user",
                "content": "Shots so far:\n"
                + _shots_json(project)
                + "\n\nDirect these transcript turns:\n"
                + _turns_json(turns),
            },
        ]
        allowed_turns = {t.id for t in turns}
        known = set(project.bible.characters)
        revisable = {s.number for s in project.shots[-REVEAL_WINDOW:]}

        first_new = len(project.shots) + 1

        def check(out: DirectorOutput) -> list[str]:
            errors = []
            cast = known | {c.id for c in out.new_characters}
            startable = revisable | set(range(first_new, first_new + len(out.shots)))
            for o in out.outfit_changes:
                if o.character_id not in cast:
                    errors.append(f"outfit_changes: character_id {o.character_id!r} is unknown")
                if o.from_shot not in startable:
                    errors.append(f"outfit_changes: from_shot {o.from_shot} is not one of {sorted(startable)}")
                if o.look_id != EVERYDAY and not (o.label.strip() and o.clothes.strip()):
                    errors.append(f"outfit_changes: {o.look_id!r} needs a label and the clothes")
            for n, s in enumerate(out.shots, start=1):
                if unknown := set(s.character_ids) - cast:
                    errors.append(f"shot {n}: character_ids {sorted(unknown)} are not in the bible or new_characters")
                if bad := set(s.source_turn_ids) - allowed_turns:
                    errors.append(f"shot {n}: source_turn_ids {sorted(bad)} are not among {sorted(allowed_turns)}")
            for u in out.updated_shots:
                if u.number not in revisable:
                    errors.append(f"updated_shots: shot {u.number} is not one of the last shots {sorted(revisable)}")
                if unknown := set(u.character_ids) - cast:
                    errors.append(f"updated shot {u.number}: character_ids {sorted(unknown)} are unknown")
            return errors

        return await self._parse(messages, DirectorOutput, effort, operation, check)

    async def _parse[M: BaseModel](
        self,
        messages: list[dict[str, Any]],
        schema: type[M],
        effort: Effort,
        operation: str,
        check: Callable[[M], list[str]] | None,
    ) -> M:
        model = self._settings.director
        for attempt in (1, 2):

            async def call(msgs: list[dict[str, Any]] = messages) -> tuple[tuple[M | None, str], Usage]:
                completion = await self._client.chat.completions.parse(
                    model=model,
                    messages=msgs,  # type: ignore[arg-type]
                    response_format=schema,
                    reasoning_effort=effort,
                )
                u = completion.usage
                cached = u.prompt_tokens_details.cached_tokens if u and u.prompt_tokens_details else None
                usage = Usage(
                    token_cost(model, u.prompt_tokens if u else None, u.completion_tokens if u else None, cached),
                    u.prompt_tokens if u else None,
                    u.completion_tokens if u else None,
                    cached,
                )
                message = completion.choices[0].message
                return (message.parsed, message.content or ""), usage

            try:
                parsed, raw = await self._caller.call(model, operation, call, self._policy)
                problem = "no structured output" if parsed is None else None
            except ValidationError as e:  # the SDK validates the JSON against the schema
                parsed, raw, problem = None, "", _short(e)
            if parsed is not None and check is not None:
                errors = check(parsed)
                problem = "; ".join(errors) if errors else None
            if problem is None and parsed is not None:
                return parsed
            if attempt == 2:
                raise InvalidModelOutputError(model, problem or "invalid output")
            messages = [
                *messages,
                {"role": "assistant", "content": raw or "(invalid)"},
                {"role": "user", "content": f"That output failed validation: {problem}. Return a corrected answer."},
            ]
        raise AssertionError("unreachable")  # pragma: no cover

    def _to_port(self, out: DirectorOutput, project: Project, turns: Sequence[TranscriptTurn]) -> DirectedTurn:
        """Durations come from the turn timings, never from the model (ADR 0002)."""
        try:
            characters = tuple(_character(c) for c in out.new_characters if c.id not in project.bible)
        except InvalidValueError as e:
            raise InvalidModelOutputError(self._settings.director, str(e)) from e
        by_id = {t.id: t for t in turns}
        shots_per_turn = Counter(tid for s in out.shots for tid in s.source_turn_ids)
        drafts = []
        for s in out.shots:
            duration = sum(by_id[tid].duration_ms // shots_per_turn[tid] for tid in s.source_turn_ids)
            drafts.append(
                ShotDraft(
                    framing=Framing(s.framing),
                    character_ids=tuple(s.character_ids),
                    setting=s.setting,
                    action=s.action,
                    dialogue=s.dialogue,
                    source_turn_ids=tuple(s.source_turn_ids),
                    duration_ms=max(1, duration),
                )
            )
        by_number = {s.number: s.id for s in project.shots}
        revisions = tuple(
            ShotRevision(by_number[u.number], tuple(u.character_ids), u.action.strip())
            for u in out.updated_shots
            if u.number in by_number
        )
        looks = tuple(
            LookChange(o.character_id, o.look_id, o.label.strip(), o.clothes.strip(), o.from_shot)
            for o in out.outfit_changes
        )
        return DirectedTurn(characters, tuple(drafts), revisions, out.refusal.strip(), looks)


def _character(c: CharacterOut) -> Character:
    return Character(c.id, c.name, c.canonical_description)


def _bible_message(characters: Sequence[Character]) -> str:
    # Stable prefix part 2: sorted and compact, so it only changes when the cast changes.
    rows: list[dict[str, Any]] = []
    for c in characters:
        row: dict[str, Any] = {"id": c.id, "name": c.name, "canonical_description": c.canonical_description}
        if c.looks:
            row["looks"] = [{"look_id": lk.id, "label": lk.label, "clothes": lk.clothes} for lk in c.looks]
        rows.append(row)
    return "Character bible:\n" + json.dumps(sorted(rows, key=lambda r: r["id"]), ensure_ascii=False)


def _turns_json(turns: Sequence[TranscriptTurn]) -> str:
    return json.dumps(
        [{"id": t.id, "start_ms": t.start_ms, "end_ms": t.end_ms, "text": t.for_director} for t in turns],
        ensure_ascii=False,
    )


def _shots_json(project: Project) -> str:
    rows = []
    for s in project.shots:
        row: dict[str, Any] = {
            "number": s.number,
            "framing": s.framing.value,
            "character_ids": list(s.character_ids),
            "action": s.action,
        }
        wearing = {c: look.id for c in s.character_ids if (look := project.look_in(s.id, c)) is not None}
        if wearing:
            row["looks"] = wearing  # who is out of their everyday clothes in this shot
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False) if rows else "[]"


def _short(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors(include_input=False)[:5])
