"""Domain: entities, value objects and story rules. Pure Python, no I/O, no frameworks."""

from frameteller.domain.animatic import Animatic, AnimaticClip
from frameteller.domain.characters import CastStatus, Character, CharacterBible
from frameteller.domain.errors import (
    CastNotApprovedError,
    DomainError,
    InvalidValueError,
    MissingReferenceError,
    PanelNotReadyError,
    RevisionOrderError,
    ShotOrderError,
    UnknownCharacterError,
    UnknownObjectError,
    UnknownShotError,
    UnknownTurnError,
)
from frameteller.domain.media import MediaRef
from frameteller.domain.panels import Box, CanvasTransform, MaskBitmap, ObjectMask, Panel, PanelStatus, Point, Size
from frameteller.domain.project import Project
from frameteller.domain.shots import Framing, Shot
from frameteller.domain.style import PanelStyle
from frameteller.domain.timing import MIN_SHOT_MS, split_duration
from frameteller.domain.transcript import TranscriptTurn

__all__ = [
    "MIN_SHOT_MS",
    "Animatic",
    "AnimaticClip",
    "Box",
    "CanvasTransform",
    "CastNotApprovedError",
    "CastStatus",
    "Character",
    "CharacterBible",
    "DomainError",
    "Framing",
    "InvalidValueError",
    "MaskBitmap",
    "MediaRef",
    "MissingReferenceError",
    "ObjectMask",
    "Panel",
    "PanelNotReadyError",
    "PanelStatus",
    "PanelStyle",
    "Point",
    "Project",
    "RevisionOrderError",
    "Shot",
    "ShotOrderError",
    "Size",
    "TranscriptTurn",
    "UnknownCharacterError",
    "UnknownObjectError",
    "UnknownShotError",
    "UnknownTurnError",
    "split_duration",
]
