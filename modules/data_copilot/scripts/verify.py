"""Semantic verification of an analysis result against the question.

Adapted from .reference/data-agent's SemanticVerifier/nodes.semantic_verify.
This is NOT a syntax check (execution errors are handled by the repair path);
it judges whether the produced output actually answers the question.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List

_SYSTEM = (
    "You are a strict verifier. Given a question, the Python code that ran, and "
    "its printed output, decide whether the output actually and correctly answers "
    "the question. Reply on the first line with exactly 'STATUS: OK' or "
    "'STATUS: REVISE'. If REVISE, add a line 'HYPOTHESES: <concrete fixes>'. "
    "Default to REVISE when uncertain."
)
_STATUS_RE = re.compile(r"STATUS:\s*(OK|REVISE)", re.IGNORECASE)
_HYP_RE = re.compile(r"HYPOTHESES:\s*(.+)", re.IGNORECASE | re.DOTALL)


def parse_verdict(text: str) -> Dict[str, str]:
    """Parse the verifier reply into a structured verdict.

    Args:
        text: The verifier model's reply.

    Returns:
        ``{"status": "OK"|"REVISE", "hypotheses": str}``. Unclear replies
        default to ``REVISE`` (fail-safe).
    """
    m = _STATUS_RE.search(text)
    status = m.group(1).upper() if m else "REVISE"
    hyp_match = _HYP_RE.search(text)
    hypotheses = hyp_match.group(1).strip() if hyp_match else ""
    return {"status": status, "hypotheses": hypotheses}


def build_messages(question: str, code: str, output: str) -> List[dict]:
    """Build the verifier chat messages.

    Args:
        question: The user's question.
        code: The code that produced the output.
        output: The captured stdout.

    Returns:
        OpenAI-format message list.
    """
    user = f"Question: {question}\n\n" f"Code:\n```python\n{code}\n```\n\n" f"Output:\n{output}\n"
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def verify(
    question: str,
    code: str,
    output: str,
    chat_fn: Callable[[List[dict]], str],
) -> Dict[str, str]:
    """Ask the verifier model whether *output* answers *question*.

    Args:
        question: The user's question.
        code: The code that produced the output.
        output: The captured stdout.
        chat_fn: Callable mapping messages -> model text (bound to the verify role).

    Returns:
        The parsed verdict from :func:`parse_verdict`.
    """
    return parse_verdict(chat_fn(build_messages(question, code, output)))
