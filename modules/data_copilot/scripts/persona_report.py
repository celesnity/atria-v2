"""Compose a grounded Markdown persona report from validated personas.

Ported (simplified) from .reference/data-agent's report_generator: personas are
ranked by priority_score and the model writes a grounded narrative — no invented
numbers. The report role's chat_fn does the writing (no instructor dependency).
"""

from __future__ import annotations

import json
from typing import Callable, List

from report import _UNVERIFIED  # type: ignore[import-not-found]

_SYSTEM = (
    "You are a data analyst writing a concise Markdown persona report for "
    "executives. Ground every statement in the provided persona JSON — do not "
    "invent numbers. For each persona give a short business interpretation, its "
    "priority, and the recommended actions. End with a one-paragraph conclusion. "
    "No tables."
)


def build_messages(personas: List[dict], question: str) -> List[dict]:
    """Build the report chat messages with personas ranked by priority_score.

    Args:
        personas: The validated persona list.
        question: The user's original request.

    Returns:
        OpenAI-format message list.
    """
    ranked = sorted(personas, key=lambda p: p.get("priority_score", 0), reverse=True)
    user = (
        f"Request: {question}\n\n"
        f"Personas (ranked by priority, JSON):\n{json.dumps(ranked, ensure_ascii=False)}\n"
    )
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def render_report(
    personas: List[dict],
    question: str,
    chat_fn: Callable[[List[dict]], str],
    *,
    verified: bool = True,
) -> str:
    """Render the persona narrative markdown.

    Args:
        personas: The validated persona list.
        question: The user's request.
        chat_fn: Callable mapping messages -> model text (bound to the report role).
        verified: When ``False``, prepend the shared UNVERIFIED banner.

    Returns:
        The Markdown report string.
    """
    body = chat_fn(build_messages(personas, question))
    return body if verified else _UNVERIFIED + body
