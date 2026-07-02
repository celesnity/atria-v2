"""Compose a grounded Markdown report from a verified analysis result.

Adapted from .reference/data-agent's report generator: the report is grounded in
the actual printed output and produced figures, and must not introduce claims
absent from that evidence.
"""

from __future__ import annotations

from typing import Callable, List

_SYSTEM = (
    "You are a data analyst writing a concise Markdown report. Ground every "
    "statement in the provided output — do not invent numbers. Reference figures "
    "by their file path. Keep it tight: a short answer, the key evidence, and "
    "any figures. Do not add further suggestions at the end."
)
_UNVERIFIED = (
    "> ⚠️ **UNVERIFIED** — the analysis loop did not confirm this result "
    "(repair/verify budget exhausted). Treat the numbers below as provisional "
    "and review the code and output before relying on them.\n\n"
)


def build_messages(question: str, output: str, figures: List[str]) -> List[dict]:
    """Build the report chat messages.

    Args:
        question: The user's question.
        output: The verified stdout to ground the report in.
        figures: Paths to any produced figures.

    Returns:
        OpenAI-format message list.
    """
    fig_lines = "\n".join(f"- {f}" for f in figures) if figures else "(none)"
    user = f"Question: {question}\n\n" f"Computed output:\n{output}\n\n" f"Figures:\n{fig_lines}\n"
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def generate_report(
    question: str,
    output: str,
    figures: List[str],
    chat_fn: Callable[[List[dict]], str],
    verified: bool = True,
) -> str:
    """Generate a grounded Markdown report.

    Args:
        question: The user's question.
        output: The stdout to ground the report in.
        figures: Paths to any produced figures.
        chat_fn: Callable mapping messages -> model text (bound to the report role).
        verified: When ``False``, prepend an UNVERIFIED warning banner.

    Returns:
        The Markdown report string.
    """
    body = chat_fn(build_messages(question, output, figures))
    return body if verified else _UNVERIFIED + body
