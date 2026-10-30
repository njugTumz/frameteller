"""The continuity supervisor's adapters: rubric files and the reviewer models (ADR 0012, 0013)."""

from pathlib import Path

from frameteller.application.rubrics import Rubric, RubricError, parse_rubric
from frameteller.infrastructure.review.fallback import FallbackReviewer
from frameteller.infrastructure.review.reviewer import ChatReviewer, GlimmerReviewerAdapter, SparkReviewerAdapter
from frameteller.infrastructure.review.warmth import GlimmerLease, ModalGlimmerWarmer, WarmGatedReviewer


class FileRubricLibrary:
    """RubricLibrary over agents/*.md. Read on every review (they are small), so an edited rubric applies at once
    and its new hash is recorded with the next verdict."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def get(self, rubric_id: str) -> Rubric:
        if not rubric_id.replace("-", "").isalnum():
            raise RubricError(f"bad rubric id {rubric_id!r}")
        path = self._folder / f"{rubric_id}.md"
        try:
            text = path.read_text("utf-8")
        except OSError as e:
            raise RubricError(f"rubric {rubric_id} not found in {self._folder}") from e
        rubric = parse_rubric(text)
        if rubric.id != rubric_id:
            raise RubricError(f"{path.name} declares id {rubric.id!r}")
        return rubric


__all__ = [
    "ChatReviewer",
    "FallbackReviewer",
    "FileRubricLibrary",
    "GlimmerLease",
    "GlimmerReviewerAdapter",
    "ModalGlimmerWarmer",
    "SparkReviewerAdapter",
    "WarmGatedReviewer",
]
