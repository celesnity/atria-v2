"""Helpers for normalizing tool output into LLM message content."""

from __future__ import annotations

import json


def as_text(value: object) -> str:
    """Coerce a tool result into a string for use as message content.

    Message ``content`` must be a string: the LLM API serializer and the
    tiktoken-based token counter both assume it. Most tools already return a
    string, but some (e.g. ``get_subagent_output``) return a structured
    dict/list. Serialize those as JSON so
    downstream code never receives a non-string.

    Args:
        value: The raw tool result (string, dict, list, or other).

    Returns:
        ``value`` unchanged if it is already a string, ``""`` for ``None``,
        otherwise a JSON (or ``str()`` fallback) rendering.
    """
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)
