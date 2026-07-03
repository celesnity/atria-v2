"""Heuristic chart-type detection for a result table.

Produces chart ``suggestions`` in the shape the atria web ``data_message``
payload consumes. Each suggestion carries the base keys (``chart_type``, ``x``,
``y``, ``title``) plus the richer fields the web UI renders — ``description``,
``labels`` (series key → display name), ``units`` (series key → unit label),
and, for mixed charts, ``combo`` (series key → ``'bar'``/``'line'``) with
``secondaryAxis`` (series keys on the right-hand axis) and ``normalized`` (radar
0–100 flag). Deterministic and LLM-free so it is cheap and reproducible.
"""

from __future__ import annotations

import re
from typing import Dict, List

_TEMPORAL = re.compile(r"(date|time|month|year|day|week|quarter|thang|nam)", re.IGNORECASE)

# When two numeric columns' typical magnitudes differ by at least this factor, a
# combo chart (big measure on bars, small measure on a secondary-axis line) reads
# far better than a shared-axis grouped bar.
_COMBO_MAGNITUDE_RATIO = 50.0


def _mean_magnitude(rows: List[dict], key: str) -> float:
    """Mean absolute numeric magnitude of *key* across *rows* (0 when none parse)."""
    total = 0.0
    count = 0
    for row in rows:
        val = row.get(key)
        try:
            num = abs(float(val))
        except (TypeError, ValueError):
            continue
        total += num
        count += 1
    return total / count if count else 0.0


def detect_suggestions(
    columns: List[dict], rows: List[dict], max_suggestions: int = 4
) -> List[Dict[str, object]]:
    """Return up to *max_suggestions* chart specs for the given result table.

    Args:
        columns: ``[{"name", "type"}]`` where ``type`` is one of
            ``number``/``string``/``date``/``bool``.
        rows: The result rows (used for the pie/radar size heuristics and to
            compare numeric magnitudes for combo detection).
        max_suggestions: Cap on the number of specs returned.

    Returns:
        A list of suggestion dicts. Each always has ``chart_type``, ``x``,
        ``y``, ``title``, ``description``, ``labels`` and ``units``; ``combo``
        suggestions additionally carry ``combo`` and ``secondaryAxis``, and
        ``radar`` suggestions carry ``normalized``. Empty when the table has no
        numeric or no categorical column.
    """
    names = [c["name"] for c in columns]
    numeric = [c["name"] for c in columns if c.get("type") == "number"]
    non_numeric = [n for n in names if n not in numeric]
    if not numeric or not non_numeric:
        return []

    x = non_numeric[0]
    y = numeric
    is_temporal = bool(_TEMPORAL.search(x))
    title = f"{y[0]} by {x}" if len(y) == 1 else f"{', '.join(y)} by {x}"
    # Result columns are already the display names, so labels is an identity map.
    labels: Dict[str, str] = {col: col for col in y}

    def _base(chart_type: str, ys: List[str], t: str, desc: str) -> Dict[str, object]:
        return {
            "chart_type": chart_type,
            "x": x,
            "y": list(ys),
            "title": t,
            "description": desc,
            "labels": {col: labels[col] for col in ys},
            "units": {},
        }

    suggestions: List[Dict[str, object]] = []

    primary = "line" if is_temporal else "bar"
    suggestions.append(
        _base(primary, y, title, f"{'Trend' if is_temporal else 'Comparison'} of {title}.")
    )
    secondary = "bar" if is_temporal else "line"
    suggestions.append(
        _base(secondary, y, title, f"Alternate {secondary} view of {title}.")
    )

    # Combo: two numeric measures whose magnitudes differ a lot read best as
    # bars (large) + a secondary-axis line (small).
    if len(y) == 2:
        m0, m1 = _mean_magnitude(rows, y[0]), _mean_magnitude(rows, y[1])
        hi, lo = (y[0], y[1]) if m0 >= m1 else (y[1], y[0])
        mag_hi, mag_lo = max(m0, m1), min(m0, m1)
        if mag_lo > 0 and mag_hi / mag_lo >= _COMBO_MAGNITUDE_RATIO:
            combo = _base(
                "combo",
                [hi, lo],
                f"{hi} vs {lo} by {x}",
                f"{hi} on bars (left axis), {lo} on a line (right axis).",
            )
            combo["combo"] = {hi: "bar", lo: "line"}
            combo["secondaryAxis"] = [lo]
            suggestions.append(combo)

    # Radar: several comparable measures across a small set of categories.
    if len(y) >= 3 and len(rows) <= 8:
        radar = _base("radar", y, f"{x} profile", f"Multi-metric radar profile by {x}.")
        radar["normalized"] = False
        suggestions.append(radar)

    # Pie: a single measure split across a small set of categories.
    if len(y) == 1 and len(rows) <= 8:
        pie = _base("pie", [y[0]], title, f"Share of {y[0]} across {x}.")
        suggestions.append(pie)

    return suggestions[:max_suggestions]
