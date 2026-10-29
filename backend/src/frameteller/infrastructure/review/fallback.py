"""FallbackReviewer: Muse Glimmer first, Muse Spark when Glimmer is cold, slow, failing or switched off (ADR 0013).

With `confirm_flags` (REVIEWER=screen) Glimmer is the screen: its passes stand, and anything it flags is reviewed
again by Spark, whose verdict decides. The eval chose this: Glimmer missed no failure and every image it passed
was clean, but it flagged a third of the clean ones (docs/supervisor-eval.md).

Glimmer runs on one GPU on Modal that scales to zero. A request to a cold endpoint starts it, which takes minutes:
the short timeout gives up, Spark answers this review, and the started container serves the next ones. Each
verdict names the model that served it, so the badge and the eval show which one checked a panel.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from frameteller.application.errors import ApplicationError
from frameteller.application.ports import ReviewerPort, ReviewRequest
from frameteller.domain import Decision, Verdict

log = logging.getLogger("frameteller.models")


class FallbackReviewer:
    def __init__(
        self,
        primary: ReviewerPort,
        fallback: ReviewerPort,
        *,
        primary_name: str = "glimmer",
        confirm_flags: bool = False,
        on_primary_failed: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._primary, self._fallback, self._primary_name = primary, fallback, primary_name
        self._confirm_flags, self._on_primary_failed = confirm_flags, on_primary_failed

    async def review(self, request: ReviewRequest) -> Verdict:
        try:
            verdict = await self._primary.review(request)
        except ApplicationError as e:  # timeout, cold start, 5xx, circuit open, unusable answer
            log.warning("reviewer fell back", extra={"primary": self._primary_name, "reason": str(e)[:200]})
            if self._on_primary_failed:
                await self._on_primary_failed(str(e))
            return await self._fallback.review(request)
        if self._confirm_flags and verdict.decision is not Decision.PASS:
            return await self._fallback.review(request)  # the screen flagged it: the stronger reviewer decides
        return verdict
