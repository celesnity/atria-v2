"""Stratified sampling for the eval set — pick a small, level-balanced subset.

Used by pub_bench.py to run a fast, cheap ~20% quick check by default while the
full 60-case run stays available on demand (``--full``). The sample is stratified
by ``difficulty`` (the eval's "level") so every level stays proportionally
represented, and is reproducible from a recorded seed.

Pure and deterministic given ``seed``; no I/O. Standalone self-test::

    python scripts/_sample.py
"""
from __future__ import annotations

import math
import random


def _allocate(sizes: dict[str, int], fraction: float, target: int) -> dict[str, int]:
    """Proportional per-level counts summing to ``target``.

    Each non-empty level gets ``floor(size*fraction)`` with a floor of 1 (so no
    level is ever dropped), capped at its size; the running total is then nudged
    to ``target`` by largest fractional remainder (add) / smallest (remove,
    never below 1). For difficulty 9/29/22 @ 0.2 -> Easy 2, Medium 6, Hard 4.
    """
    ideal = {k: n * fraction for k, n in sizes.items()}
    base = {k: min(sizes[k], max(1, int(math.floor(ideal[k])))) if sizes[k] else 0
            for k in sizes}
    # levels ranked by fractional remainder (desc = first to gain a slot)
    by_remainder = sorted(sizes, key=lambda k: ideal[k] - math.floor(ideal[k]),
                          reverse=True)

    cur = sum(base.values())
    guard = 0
    while cur < target and guard < 10000:
        for k in by_remainder:
            if cur >= target:
                break
            if base[k] < sizes[k]:
                base[k] += 1
                cur += 1
        guard += 1
    guard = 0
    while cur > target and guard < 10000:
        for k in reversed(by_remainder):
            if cur <= target:
                break
            if base[k] > 1:
                base[k] -= 1
                cur -= 1
        guard += 1
    return base


def stratified_sample(cases: list[dict], fraction: float, seed: int,
                      level_key: str = "difficulty") -> tuple[list[dict], dict]:
    """Return (subset, meta) — a proportional, level-balanced random sample.

    ``subset`` is sorted by ``query_id`` (file order) so the bench loop and report
    ordering stay stable. ``meta`` records everything needed to interpret and
    replay the pick: fraction, seed, per-level counts and the chosen ids.
    """
    groups: dict[str, list[dict]] = {}
    for c in cases:
        groups.setdefault(c.get(level_key), []).append(c)

    target = max(1, round(len(cases) * fraction))
    per_level = _allocate({k: len(v) for k, v in groups.items()}, fraction, target)

    rng = random.Random(seed)
    picked: list[dict] = []
    for k, group in groups.items():
        picked.extend(rng.sample(group, per_level[k]))
    picked.sort(key=lambda c: c["query_id"])

    meta = {
        "fraction": fraction,
        "seed": seed,
        "level_key": level_key,
        "mode": "proportional",
        "n_full": len(cases),
        "per_level": {str(k): per_level[k] for k in per_level},
        "picked_ids": [c["query_id"] for c in picked],
        "full": False,
    }
    return picked, meta


if __name__ == "__main__":  # pragma: no cover - smoke
    demo = ([{"query_id": f"E{i:03d}", "difficulty": "Easy"} for i in range(9)]
            + [{"query_id": f"M{i:03d}", "difficulty": "Medium"} for i in range(29)]
            + [{"query_id": f"H{i:03d}", "difficulty": "Hard"} for i in range(22)])
    sub, m = stratified_sample(demo, 0.2, seed=1)
    print("per_level:", m["per_level"], "total:", len(sub))
    assert m["per_level"] == {"Easy": 2, "Medium": 6, "Hard": 4}, m["per_level"]
    assert len(sub) == 12
    print("ok")
