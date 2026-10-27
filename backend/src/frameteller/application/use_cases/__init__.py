"""Use cases: one class per user intent, each with a single async execute()."""

from frameteller.application.use_cases.approve_cast import ApproveCast
from frameteller.application.use_cases.build_character_bible import BuildCharacterBible
from frameteller.application.use_cases.direct_turn import DirectTurn
from frameteller.application.use_cases.edit_panel_appearance import EditPanelAppearance
from frameteller.application.use_cases.export_animatic import ExportAnimatic
from frameteller.application.use_cases.generate_character_reference import GenerateCharacterReference
from frameteller.application.use_cases.generate_panel import GeneratePanel
from frameteller.application.use_cases.move_panel_object import MovePanelObject
from frameteller.application.use_cases.pre_segment_panel import PreSegmentPanel, character_mask_id
from frameteller.application.use_cases.reorder_shots import ReorderShots
from frameteller.application.use_cases.segment_object_at_point import SegmentObjectAtPoint

__all__ = [
    "ApproveCast",
    "BuildCharacterBible",
    "DirectTurn",
    "EditPanelAppearance",
    "ExportAnimatic",
    "GenerateCharacterReference",
    "GeneratePanel",
    "MovePanelObject",
    "PreSegmentPanel",
    "ReorderShots",
    "SegmentObjectAtPoint",
    "character_mask_id",
]
