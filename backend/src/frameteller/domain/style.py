"""How the storyboard is drawn. Chosen when a story starts; every panel and reference sheet follows it."""

from __future__ import annotations

from enum import StrEnum


class PanelStyle(StrEnum):
    PENCIL = "pencil"
    PAPER_CUTOUT = "paper_cutout"
