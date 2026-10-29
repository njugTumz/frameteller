""" "Read it to me" voices (ADR 0015): the curated list and a short preview of each."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from frameteller.application.use_cases.voices import DEFAULT_VOICE
from frameteller.interface.dto import VoiceOut, VoicesOut
from frameteller.interface.errors import error_response
from frameteller.interface.routes.deps import Deps

router = APIRouter(tags=["voices"])

VOICE = r"^[A-Za-z]{2,3}-[A-Za-z]{2,4}-[A-Za-z]{3,40}$"
NOT_SET_UP = "Read it to me isn't available right now. Narrate the story or use the teleprompter."


@router.get("/voices", response_model=VoicesOut)
async def list_voices(c: Deps) -> VoicesOut:
    """The voices and languages offered. `available` is false when Text-to-Speech is not configured."""
    if c.list_voices is None:
        return VoicesOut(available=False, default=DEFAULT_VOICE, voices=[])
    voices = await c.list_voices.execute()
    return VoicesOut(available=bool(voices), default=DEFAULT_VOICE, voices=[VoiceOut.of(v) for v in voices])


@router.get("/voices/{voice}/preview", response_class=Response, responses={200: {"content": {"audio/wav": {}}}})
async def preview_voice(
    voice: Annotated[str, Path(pattern=VOICE)],
    c: Deps,
    language: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")] = "en",
) -> Response:
    """One sentence in the voice and language, as WAV. Synthesized once, then kept."""
    if c.preview_voice is None:
        return error_response(503, "speech_unavailable", NOT_SET_UP)
    data = await c.preview_voice.execute(voice, language)
    return Response(data, media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400"})
