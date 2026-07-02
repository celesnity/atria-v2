"""Static pre-execution guardrails for generated analysis code.

Enforced in code, not left to the prompt: code that reaches out to the network,
spawns processes, escapes the run directory, or does dynamic imports is blocked
before it ever runs. Analysis code only needs to read the dataset, compute over
it in memory, print results, and save figures into the run directory.
"""

from __future__ import annotations

import re
from typing import Dict, List

_NETWORK_MODULES = "socket|requests|urllib|http|httpx|aiohttp|ftplib|smtplib"
_PROCESS_MODULES = "subprocess|multiprocessing"

# (compiled pattern, human-readable reason). Best-effort static screen; the
# runtime is already sandboxed. Import rules match both `import X` and
# `from X import ...` (incl. comma lists / aliases). The open() rule only blocks
# WRITE/APPEND mode targeting an absolute or parent path — benign reads and
# writes into the run dir are allowed. Keyword-arg open(mode=...) is a known
# best-effort gap.
_RULES = [
    (re.compile(rf"(?m)^\s*(?:import|from)\s+[^\n]*\b(?:{_NETWORK_MODULES})\b"),
     "network access is not allowed"),
    (re.compile(rf"(?m)^\s*(?:import|from)\s+[^\n]*\b(?:{_PROCESS_MODULES})\b"),
     "spawning processes is not allowed"),
    (re.compile(r"\bos\.(system|popen|exec[lv]?[pe]*|spawn\w*)\s*\("),
     "shell/process execution is not allowed"),
    (re.compile(r"\bfrom\s+os\s+import\s+[^\n]*\b(system|popen|exec\w*|spawn\w*)\b"),
     "shell/process execution is not allowed"),
    (re.compile(r"\b__import__\s*\("), "dynamic __import__ is not allowed"),
    (re.compile(r"\b(eval|exec)\s*\("), "eval/exec is not allowed"),
    (re.compile(r"\bshutil\.rmtree\s*\("), "recursive delete is not allowed"),
    (re.compile(r"\bfrom\s+shutil\s+import\s+[^\n]*\brmtree\b"),
     "recursive delete is not allowed"),
    (re.compile(r"\bos\.(remove|unlink)\s*\("), "file deletion is not allowed"),
    (re.compile(r"\bfrom\s+os\s+import\s+[^\n]*\b(remove|unlink)\b"),
     "file deletion is not allowed"),
    (re.compile(
        r"open\s*\(\s*f?['\"](/|[a-zA-Z]:\\|\.\.)[^'\"]*['\"]\s*,\s*"
        r"f?['\"][^'\"]*[wa][^'\"]*['\"]"),
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
