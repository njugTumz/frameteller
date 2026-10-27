"""Animatic timing: how a turn's narration time is shared between the shots it produced (ADR 0008)."""

from __future__ import annotations

from collections.abc import Sequence

MIN_SHOT_MS = 1500


def split_duration(total_ms: int, words: Sequence[int], min_ms: int = MIN_SHOT_MS) -> list[int]:
    """Split `total_ms` across shots in proportion to their word counts.

    Every shot gets at least `min_ms` when the turn is long enough for that; otherwise the turn is split evenly.
    The parts always add up to the turn (at least 1 ms per shot), so panels stay in step with the narration.
    """
    n = len(words)
    if n == 0:
        return []
    total_ms = max(total_ms, n)
    floor = min_ms if total_ms >= min_ms * n else total_ms // n
    weights = [max(1, w) for w in words]
    floored: set[int] = set()
    while True:  # give the floor to every shot whose share falls below it, then re-share the rest
        free = [i for i in range(n) if i not in floored]
        budget = total_ms - floor * len(floored)
        weight = sum(weights[i] for i in free)
        shares = {i: budget * weights[i] / weight for i in free}
        low = {i for i, share in shares.items() if share < floor}
        if not low:
            break
        floored |= low
    exact = [float(floor) if i in floored else shares[i] for i in range(n)]
    parts = [int(x) for x in exact]
    by_remainder = sorted(range(n), key=lambda i: exact[i] - parts[i], reverse=True)
    for i in by_remainder[: total_ms - sum(parts)]:  # largest remainder: the parts sum exactly to the turn
        parts[i] += 1
    return parts
