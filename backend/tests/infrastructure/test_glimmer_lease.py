"""Glimmer only while warm (ADR 0013): visitors' reviews never wake the GPU, a lost Glimmer revokes the lease."""

from datetime import timedelta

from frameteller.application.errors import ModelTimeoutError
from frameteller.application.ports import ReviewRequest
from frameteller.application.rubrics import RubricSet
from frameteller.domain import MediaRef, PanelStyle
from frameteller.infrastructure.review import FallbackReviewer, GlimmerLease, WarmGatedReviewer
from frameteller.infrastructure.review.warmth import LEASE_KEY, MAX_LEASE_MINUTES
from tests.fakes import FakeReviewer, FixedClock, InMemoryMediaStorage, InMemoryRubricLibrary, verdict

REQUEST = ReviewRequest((MediaRef("p.webp"),), RubricSet((InMemoryRubricLibrary().get("shot"),)), PanelStyle.PENCIL)


def gated(glimmer: FakeReviewer, spark: FakeReviewer, lease: GlimmerLease) -> WarmGatedReviewer:
    screen = FallbackReviewer(glimmer, spark, confirm_flags=True, on_primary_failed=lease.lost)
    return WarmGatedReviewer(screen, spark, lease)


async def test_without_a_lease_spark_reviews_and_glimmer_is_never_called() -> None:
    lease = GlimmerLease(InMemoryMediaStorage(), FixedClock())
    glimmer, spark = FakeReviewer(verdict(model="muse-glimmer")), FakeReviewer(verdict(model="muse-spark-1.3"))
    v = await gated(glimmer, spark, lease).review(REQUEST)
    assert v.model == "muse-spark-1.3"
    assert glimmer.requests == []  # no request: a cold container is never started by a visitor


async def test_while_the_lease_holds_glimmer_screens_and_after_it_expires_spark_reviews_alone() -> None:
    clock = FixedClock()
    lease = GlimmerLease(InMemoryMediaStorage(), clock)
    glimmer, spark = FakeReviewer(verdict(model="muse-glimmer")), FakeReviewer(verdict(model="muse-spark-1.3"))
    reviewer = gated(glimmer, spark, lease)
    await lease.grant(10)
    assert (await reviewer.review(REQUEST)).model == "muse-glimmer"
    clock.current += timedelta(minutes=10, seconds=1)
    assert (await reviewer.review(REQUEST)).model == "muse-spark-1.3"
    assert len(glimmer.requests) == 1


async def test_glimmer_failing_under_a_lease_revokes_it() -> None:
    lease = GlimmerLease(InMemoryMediaStorage(), FixedClock())
    glimmer = FakeReviewer(ModelTimeoutError("muse-glimmer", "cold start"), verdict(model="muse-glimmer"))
    spark = FakeReviewer(verdict(model="muse-spark-1.3"))
    reviewer = gated(glimmer, spark, lease)
    await lease.grant(10)
    assert (await reviewer.review(REQUEST)).model == "muse-spark-1.3"  # this review: Spark
    assert await lease.warm_until() is None
    assert (await reviewer.review(REQUEST)).model == "muse-spark-1.3"  # and no more tries until renewed
    assert len(glimmer.requests) == 1


async def test_the_lease_is_stored_so_a_restart_keeps_it_and_is_capped() -> None:
    storage, clock = InMemoryMediaStorage(), FixedClock()
    until = await GlimmerLease(storage, clock).grant(600)
    assert until == clock.now() + timedelta(minutes=MAX_LEASE_MINUTES)
    assert LEASE_KEY in storage.files
    assert await GlimmerLease(storage, clock).warm_until() == until  # a new replica reads it back


async def test_an_unreadable_lease_means_cold() -> None:
    storage = InMemoryMediaStorage()
    await storage.put(LEASE_KEY, b"not json", "application/json")
    assert await GlimmerLease(storage, FixedClock()).warm_until() is None
