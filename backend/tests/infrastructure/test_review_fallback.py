"""FallbackReviewer (ADR 0013): Glimmer first, Spark when Glimmer is cold, slow, failing or answers badly."""

import pytest

from frameteller.application.errors import (
    InvalidModelOutputError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from frameteller.application.ports import ReviewRequest
from frameteller.application.rubrics import RubricSet
from frameteller.domain import Decision, Issue, MediaRef, PanelStyle, Severity
from frameteller.infrastructure.review import FallbackReviewer
from tests.fakes import FakeReviewer, InMemoryRubricLibrary, verdict

REQUEST = ReviewRequest((MediaRef("p.webp"),), RubricSet((InMemoryRubricLibrary().get("shot"),)), PanelStyle.PENCIL)


async def test_glimmer_answers_when_it_is_warm() -> None:
    glimmer, spark = FakeReviewer(verdict(model="muse-glimmer")), FakeReviewer(verdict(model="muse-spark-1.3"))
    v = await FallbackReviewer(glimmer, spark).review(REQUEST)
    assert v.model == "muse-glimmer"
    assert spark.requests == []


@pytest.mark.parametrize(
    "failure",
    [
        ModelTimeoutError("muse-glimmer", "cold start"),
        ModelUnavailableError("muse-glimmer", "circuit open"),
        InvalidModelOutputError("muse-glimmer", "issues: field required"),
    ],
)
async def test_spark_reviews_when_glimmer_times_out_is_down_or_answers_badly(failure: Exception) -> None:
    glimmer, spark = FakeReviewer(failure), FakeReviewer(verdict(model="muse-spark-1.3"))
    v = await FallbackReviewer(glimmer, spark).review(REQUEST)
    assert v.model == "muse-spark-1.3"  # the verdict says which model served it
    assert len(glimmer.requests) == len(spark.requests) == 1


async def test_an_error_that_is_not_a_model_failure_is_not_hidden() -> None:
    glimmer = FakeReviewer(ValueError("a bug"))
    with pytest.raises(ValueError, match="a bug"):
        await FallbackReviewer(glimmer, FakeReviewer()).review(REQUEST)


async def test_as_a_screen_glimmer_passes_stand_and_its_flags_go_to_spark() -> None:
    flagged = verdict(Decision.ASK, Issue("CONT-07", Severity.MAJOR, "style"), model="muse-glimmer")
    glimmer = FakeReviewer(verdict(model="muse-glimmer"), flagged)
    spark = FakeReviewer(verdict(model="muse-spark-1.3"))
    screen = FallbackReviewer(glimmer, spark, confirm_flags=True)
    assert (await screen.review(REQUEST)).model == "muse-glimmer"  # a pass stands
    assert spark.requests == []
    assert (await screen.review(REQUEST)).model == "muse-spark-1.3"  # a flag is decided by Spark
    assert len(spark.requests) == 1
