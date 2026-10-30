"""Use cases: one class per user intent, each with a single async execute()."""

from frameteller.application.use_cases.approve_cast import ApproveCast, CastReview
from frameteller.application.use_cases.build_character_bible import BuildCharacterBible
from frameteller.application.use_cases.cast_references import GenerateCastReferences
from frameteller.application.use_cases.compose_panel import ComposePanel
from frameteller.application.use_cases.correct_transcript import CorrectTranscript
from frameteller.application.use_cases.direct_turn import DirectedShots, DirectTurn
from frameteller.application.use_cases.edit_panel_appearance import EditPanelAppearance
from frameteller.application.use_cases.edit_panel_by_command import EditPanelByCommand
from frameteller.application.use_cases.edit_story import DeleteShot, MergeBeats, RemoveBeat
from frameteller.application.use_cases.export_animatic import AnimaticOptions, ExportAnimatic, RequestAnimaticExport
from frameteller.application.use_cases.export_storyboard_pdf import ExportStoryboardPdf
from frameteller.application.use_cases.generate_character_reference import GenerateCharacterReference
from frameteller.application.use_cases.generate_panel import GeneratePanel
from frameteller.application.use_cases.manage_cast import MergeCharacters, Merged, RemoveCharacter, RenameCharacter
from frameteller.application.use_cases.move_panel_object import MovePanelObject
from frameteller.application.use_cases.narration import DeleteNarration
from frameteller.application.use_cases.pre_segment_panel import PreSegmentPanel, character_mask_id
from frameteller.application.use_cases.projects import CreateProject, FindShot, GetProject
from frameteller.application.use_cases.read_script import ReadControl, ReadingOptions, ReadScript
from frameteller.application.use_cases.reorder_shots import ReorderShots
from frameteller.application.use_cases.requests import (
    JobTicket,
    RequestCastReferences,
    RequestPanelEdit,
    RequestPanelRender,
)
from frameteller.application.use_cases.segment_object_at_point import SegmentObjectAtPoint, Selection
from frameteller.application.use_cases.share import OpenShare, RevokeShare, SharePreview, ShareProject
from frameteller.application.use_cases.status import GetStudioStatus, StudioStatus
from frameteller.application.use_cases.story_director import StoryDirector, TranscriptCorrection
from frameteller.application.use_cases.supervise import (
    AcceptReview,
    ApplySuggestedFix,
    ReviewSheet,
    SetContinuityChecks,
    SupervisePanel,
)
from frameteller.application.use_cases.transcribe_instruction import MAX_DICTATION_MS, TranscribeInstruction
from frameteller.application.use_cases.voice_session import Beat, ClientInput, RunVoiceSession
from frameteller.application.use_cases.voices import ListVoices, OfferedVoice, PreviewVoice

__all__ = [
    "MAX_DICTATION_MS",
    "AcceptReview",
    "AnimaticOptions",
    "ApplySuggestedFix",
    "ApproveCast",
    "Beat",
    "BuildCharacterBible",
    "CastReview",
    "ClientInput",
    "ComposePanel",
    "CorrectTranscript",
    "CreateProject",
    "DeleteNarration",
    "DeleteShot",
    "DirectTurn",
    "DirectedShots",
    "EditPanelAppearance",
    "EditPanelByCommand",
    "ExportAnimatic",
    "ExportStoryboardPdf",
    "FindShot",
    "GenerateCastReferences",
    "GenerateCharacterReference",
    "GeneratePanel",
    "GetProject",
    "GetStudioStatus",
    "JobTicket",
    "ListVoices",
    "MergeBeats",
    "MergeCharacters",
    "Merged",
    "MovePanelObject",
    "OfferedVoice",
    "OpenShare",
    "PreSegmentPanel",
    "PreviewVoice",
    "ReadControl",
    "ReadScript",
    "ReadingOptions",
    "RemoveBeat",
    "RemoveCharacter",
    "RenameCharacter",
    "ReorderShots",
    "RequestAnimaticExport",
    "RequestCastReferences",
    "RequestPanelEdit",
    "RequestPanelRender",
    "ReviewSheet",
    "RevokeShare",
    "RunVoiceSession",
    "SegmentObjectAtPoint",
    "Selection",
    "SetContinuityChecks",
    "SharePreview",
    "ShareProject",
    "StoryDirector",
    "StudioStatus",
    "SupervisePanel",
    "TranscribeInstruction",
    "TranscriptCorrection",
    "character_mask_id",
]
