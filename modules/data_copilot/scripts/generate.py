"""Generate Python analysis code from a question + dataset profile.

Adapted from .reference/data-agent's programmer/nodes.generate_code: the dataset
profile is injected so the model uses real column names, and any prior execution
error or verifier hypotheses are appended to drive repair/revision.
"""

from __future__ import annotations

import json
import re
from typing import Callable, List, Optional

_CODE_RE = re.compile(r"```python([^\n]*)(.*?)```", re.DOTALL)

_SYSTEM = (
    "You are a senior data analyst. Write a single self-contained Python script "
    "that answers the user's question about the dataset. Rules: use pandas; load "
    "the dataset from the exact path given; PRINT the answer with clear labels; "
    "if a chart helps, use matplotlib with the 'Agg' backend and savefig into the "
    "current directory. If your analysis produces a final tabular result (a pandas "
    "DataFrame that answers the question), also save it to 'result.csv' in the "
    "current directory with df.to_csv('result.csv', index=False); keep it small "
    "(<= 50 rows) and tidy (the FIRST column categorical, the remaining columns "
    "numeric measures) since it is shown to the user as an interactive chart.\n"
    "PIVOT / CROSS-TAB RESULTS: when the question breaks a measure down across TWO "
    "dimensions (e.g. 'sales by region and category', 'revenue per month by "
    "channel', 'count by status and plan'), shape result.csv as a WIDE PIVOT "
    "TABLE, not a long 3-column table. Use pandas pivot_table (or groupby + "
    "unstack), then reset_index() so the primary dimension is a normal first "
    "column and each value of the secondary dimension becomes its own numeric "
    "column (fill missing cells with 0, e.g. fill_value=0). This wide layout is "
    "what the UI turns into a grouped multi-series chart. Keep it compact: if a "
    "dimension has many values, pivot only the top ~8 by the measure and bucket "
    "the rest into 'Other'. Round measures sensibly and give the columns clean, "
    "human-readable names.\n"
    "Do NOT access the network, spawn processes, or write outside the current "
    "directory. Return the code in one ```python``` block."
)


def extract_code(text: str) -> tuple[bool, str]:
    """Extract Python from ```python fenced blocks (concatenated if several).

    Args:
        text: The model response.

    Returns:
        ``(found, code)``. ``found`` is ``False`` and ``code`` empty if no block.
    """
    matches = _CODE_RE.findall(text)
    if not matches:
        return False, ""
    if len(matches) > 1:
        return True, "".join(m[1] for m in matches)
    return True, matches[-1][1]


def build_messages(
    question: str,
    profile: dict,
    prior_error: Optional[str] = None,
    hypotheses: Optional[str] = None,
) -> List[dict]:
    """Build the chat messages for code generation.

    Args:
        question: The user's natural-language question.
        profile: Dataset profile from :func:`profile.profile_dataset`.
        prior_error: Traceback/stderr from a failed run, to drive repair.
        hypotheses: Verifier suggestions, to drive semantic revision.

    Returns:
        OpenAI-format message list.
    """
    prof_json = json.dumps(
        {k: profile[k] for k in ("path", "n_rows", "n_cols", "columns", "sample") if k in profile},
        default=str,
    )
    user = (
        f"Dataset path: {profile.get('path')}\n"
        f"Dataset profile (JSON):\n{prof_json}\n\n"
        f"Question: {question}\n"
    )
    if prior_error:
        user += "\nThe previous code failed with this error — fix it:\n" f"{prior_error}\n"
    if hypotheses:
        user += "\nA verifier judged the previous result insufficient. Address:\n" f"{hypotheses}\n"
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def generate_code(
    question: str,
    profile: dict,
    chat_fn: Callable[[List[dict]], str],
    prior_error: Optional[str] = None,
    hypotheses: Optional[str] = None,
) -> str:
    """Generate analysis code, returning the extracted Python (or raw text).

    Args:
        question: The user's question.
        profile: Dataset profile.
        chat_fn: Callable mapping messages -> model text (bound to the codegen role).
        prior_error: Optional error from a prior run.
        hypotheses: Optional verifier hypotheses.

    Returns:
        The extracted Python code; if no fenced block is present, the raw text.
    """
    messages = build_messages(question, profile, prior_error, hypotheses)
    text = chat_fn(messages)
    found, code = extract_code(text)
    return code if found else text
