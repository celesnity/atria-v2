"""Reciprocal-rank fusion and small ranking utilities."""

from __future__ import annotations

from collections import Counter
from typing import Any


def rrf_fuse(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Fuse ranked id lists with reciprocal-rank fusion.

    Args:
        rankings: One ordered id list per recall channel (best first).
        k: Standard RRF damping constant.

    Returns:
        id -> fused score (higher is better).
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


def top_margin(scores: list[float]) -> float | None:
    """Relative gap between the top two scores; None if no results."""
    if not scores:
        return None
    if len(scores) == 1:
        return 1.0
    s1, s2 = scores[0], scores[1]
    if s1 <= 0:
        return 0.0
    return max(0.0, (s1 - s2) / s1)


def facet_counts(rows: list[dict[str, Any]], keys: list[str]) -> dict[str, dict[str, int]]:
    """Count value frequencies for the given keys across result rows."""
    facets: dict[str, dict[str, int]] = {}
    for key in keys:
        counter = Counter(str(row[key]) for row in rows if row.get(key) not in (None, ""))
        if counter:
            facets[key] = dict(counter.most_common())
    return facets
