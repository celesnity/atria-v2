"""Heuristic chart-type detection for a result table.

Produces chart ``suggestions`` in the shape the atria web ``data_message``
payload consumes (``ChartSuggestion``: chart_type, x, y[], title). Deterministic
and LLM-free so it is cheap and reproducible.
"""

from __future__ import annotations

import re
from typing import Dict, List

_TEMPORAL = re.compile(r"(date|time|month|year|day|week|quarter|thang|nam)", re.IGNORECASE)


def detect_suggestions(
    columns: List[dict], rows: List[dict], max_suggestions: int = 3
) -> List[Dict[str, object]]:
    """Return up to *max_suggestions* chart specs for the given result table.

    Args:
        columns: ``[{"name", "type"}]`` where ``type`` is one of
            ``number``/``string``/``date``/``bool``.
        rows: The result rows (used only for the small-set pie heuristic).
        max_suggestions: Cap on the number of specs returned.

    Returns:
        A list of ``{"chart_type", "x", "y": [...], "title"}`` dicts (possibly
        empty when the table has no numeric or no categorical column).
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

    suggestions: List[Dict[str, object]] = []
    primary = "line" if is_temporal else "bar"
    suggestions.append({"chart_type": primary, "x": x, "y": list(y), "title": title})
    secondary = "bar" if is_temporal else "line"
    suggestions.append({"chart_type": secondary, "x": x, "y": list(y), "title": title})
    if len(y) == 1 and len(rows) <= 8:
        suggestions.append({"chart_type": "pie", "x": x, "y": [y[0]], "title": title})
    return suggestions[:max_suggestions]
