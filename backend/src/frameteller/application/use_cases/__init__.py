"""Use cases: one class per user intent, each with a single async execute()."""

from frameteller.application.use_cases.approve_cast import ApproveCast, CastReview
from frameteller.application.use_cases.build_character_bible import BuildCharacterBible
from frameteller.application.use_cases.cast_references import GenerateCastReferences
from frameteller.application.use_cases.correct_transcript import CorrectTranscript
from frameteller.application.use_cases.direct_turn import DirectedShots, DirectTurn
from frameteller.application.use_cases.edit_panel_appearance import EditPanelAppearance
from frameteller.application.use_cases.edit_panel_by_command import EditPanelByCommand
from frameteller.application.use_cases.export_animatic import ExportAnimatic
from frameteller.application.use_cases.generate_character_reference import GenerateCharacterReference
from frameteller.application.use_cases.generate_panel import GeneratePanel
from frameteller.application.use_cases.manage_cast import MergeCharacters, Merged, RemoveCharacter, RenameCharacter
from frameteller.application.use_cases.move_panel_object import MovePanelObject
from frameteller.application.use_cases.narration import DeleteNarration
from frameteller.application.use_cases.pre_segment_panel import PreSegmentPanel, character_mask_id
from frameteller.application.use_cases.projects import CreateProject, FindShot, GetProject
from frameteller.application.use_cases.reorder_shots import ReorderShots
from frameteller.application.use_cases.requests import (
    JobTicket,
    RequestCastReferences,
    RequestPanelEdit,
    RequestPanelRender,
)
from frameteller.application.use_cases.segment_object_at_point import SegmentObjectAtPoint, Selection
from frameteller.application.use_cases.transcribe_instruction import MAX_DICTATION_MS, TranscribeInstruction
from frameteller.application.use_cases.voice_session import Beat, ClientInput, RunVoiceSession, TranscriptCorrection

__all__ = [
    "MAX_DICTATION_MS",
    "ApproveCast",
    "Beat",
    "BuildCharacterBible",
    "CastReview",
    "ClientInput",
    "CorrectTranscript",
    "CreateProject",
    "DeleteNarration",
    "DirectTurn",
    "DirectedShots",
    "EditPanelAppearance",
    "EditPanelByCommand",
    "ExportAnimatic",
    "FindShot",
    "GenerateCastReferences",
    "GenerateCharacterReference",
    "GeneratePanel",
    "GetProject",
    "JobTicket",
    "MergeCharacters",
    "Merged",
    "MovePanelObject",
    "PreSegmentPanel",
    "RemoveCharacter",
    "RenameCharacter",
    "ReorderShots",
    "RequestCastReferences",
    "RequestPanelEdit",
    "RequestPanelRender",
    "RunVoiceSession",
    "SegmentObjectAtPoint",
    "Selection",
    "TranscribeInstruction",
    "TranscriptCorrection",
    "character_mask_id",
]
