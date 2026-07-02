"""Static pre-execution guardrails for generated analysis code.

Enforced in code, not left to the prompt: code that reaches out to the network,
spawns processes, escapes the run directory, or does dynamic imports is blocked
before it ever runs. Analysis code only needs to read the dataset, compute over
it in memory, print results, and save figures into the run directory.
"""

from __future__ import annotations

import re
from typing import Dict, List

# (compiled pattern, human-readable reason). Substring/regex matches on source.
_RULES = [
    (re.compile(r"\bimport\s+(socket|requests|urllib|http|ftplib|smtplib)\b"),
     "network access is not allowed"),
    (re.compile(r"\bfrom\s+(socket|requests|urllib|http)\b"),
     "network access is not allowed"),
    (re.compile(r"\bimport\s+(subprocess|multiprocessing)\b"),
     "spawning processes is not allowed"),
    (re.compile(r"\bos\.(system|popen|exec[lv]?[pe]*|spawn\w*)\s*\("),
     "shell/process execution is not allowed"),
    (re.compile(r"\b__import__\s*\("), "dynamic __import__ is not allowed"),
    (re.compile(r"\b(eval|exec)\s*\("), "eval/exec is not allowed"),
    (re.compile(r"\bshutil\.rmtree\s*\("), "recursive delete is not allowed"),
    (re.compile(r"\bos\.remove\s*\(|\bos\.unlink\s*\("), "file deletion is not allowed"),
    # open(...) in a write/append mode targeting an absolute or parent path.
    (re.compile(r"open\s*\(\s*['\"](/|[a-zA-Z]:\\|\.\.)"),
     "writing outside the run directory is not allowed"),
]


def check_code(code: str) -> Dict[str, object]:
    """Statically screen generated code for disallowed operations.

    Args:
        code: The Python source to screen.

    Returns:
        ``{"allowed": bool, "reasons": list[str]}`` — ``allowed`` is ``False``
        when any rule matches; ``reasons`` lists the distinct triggered reasons.
    """
    reasons: List[str] = []
    for pattern, reason in _RULES:
        if pattern.search(code) and reason not in reasons:
            reasons.append(reason)
    return {"allowed": not reasons, "reasons": reasons}
