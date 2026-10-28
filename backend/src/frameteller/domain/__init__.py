"""Domain: entities, value objects and story rules. Pure Python, no I/O, no frameworks."""

from frameteller.domain.animatic import Animatic, AnimaticClip, AudioCut, Motion, motion_for
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
from frameteller.domain.exports import AnimaticExport
from frameteller.domain.media import MediaRef
from frameteller.domain.narration import Narration, session_of
from frameteller.domain.panels import (
    Box,
    CanvasTransform,
    CleanPlate,
    Composite,
    MaskBitmap,
    ObjectMask,
    Panel,
    PanelStatus,
    Point,
    Size,
    plate_key,
)
from frameteller.domain.project import Project
from frameteller.domain.shots import Framing, Shot
from frameteller.domain.style import PanelStyle
from frameteller.domain.timing import MIN_SHOT_MS, split_duration
from frameteller.domain.transcript import TranscriptTurn

__all__ = [
    "MIN_SHOT_MS",
    "Animatic",
    "AnimaticClip",
    "AnimaticExport",
    "AudioCut",
    "Box",
    "CanvasTransform",
    "CastNotApprovedError",
    "CastStatus",
    "Character",
    "CharacterBible",
    "CleanPlate",
    "Composite",
    "DomainError",
    "Framing",
    "InvalidValueError",
    "MaskBitmap",
    "MediaRef",
    "MissingReferenceError",
    "Motion",
    "Narration",
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
    "motion_for",
    "plate_key",
    "session_of",
    "split_duration",
]
