"""LLM summary for inject-category documents (persona / company_background)."""

from __future__ import annotations

import logging
from typing import Any
from typing import Callable

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Summarize the document into a concise briefing (max ~800 tokens) that an "
    "AI assistant can carry as background. Keep concrete facts; drop fluff."
)


def summarize_document(
    text: str, chat_fn: Callable[[list[dict[str, Any]]], str]
) -> str:
    """Return a short summary, or '' if the model call fails/returns nothing."""
    try:
        out = chat_fn([{"role": "system", "content": _SYSTEM}, {"role": "user", "content": text}])
    except Exception as exc:  # noqa: BLE001
        logger.warning("summarize failed: %s", exc)
        return ""
    return (out or "").strip()
