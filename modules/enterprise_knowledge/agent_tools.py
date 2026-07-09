"""Agent-callable tool for enterprise_knowledge: structured RAG query.

Exposes ``enterprise_knowledge_query`` so the model calls a typed tool instead
of hand-composing a ``python knowledge.py query ...`` shell command. Small
models fumbled the raw CLI (wrong path missing ``scripts/``, invented
``--user_id`` flag, probed the bare script) before getting it right. A
structured tool removes the shell surface entirely: the handler resolves
``knowledge.py`` from its own location (no CWD dependency) and builds the exact
command itself.

Registered via the SKILL.md ``tools: agent_tools.py`` frontmatter and the
module-aware skill-tool loader.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from atria.core.skill_tools import SkillToolContext, ToolSpec

_SCRIPTS = Path(__file__).resolve().parent / "scripts"
_KNOWLEDGE = _SCRIPTS / "knowledge.py"

_VALID_MODES = ("dense", "bm25", "hybrid")


def build_query_cmd(
    user_id: str,
    question: str,
    synthesize: bool = True,
    k: int = 5,
    department: str | None = None,
    mode: str = "hybrid",
) -> list[str]:
    """Build the exact ``knowledge.py query`` argv. Pure — unit-testable.

    Uses an absolute path to ``knowledge.py`` so it works regardless of the
    caller's working directory, and the correct ``--user`` flag (not
    ``--user_id``).
    """
    if mode not in _VALID_MODES:
        mode = "hybrid"
    cmd = [
        sys.executable,
        str(_KNOWLEDGE),
        "query",
        str(question),
        "--user",
        str(user_id),
        "--k",
        str(int(k)),
        "--mode",
        str(mode),
    ]
    if synthesize:
        cmd.append("--synthesize")
    if department:
        cmd += ["--department", str(department)]
    return cmd


def _run_query(
    user_id: str = "",
    question: str = "",
    synthesize: bool = True,
    k: int = 5,
    department: str | None = None,
    mode: str = "hybrid",
    **_ignored: Any,
) -> dict[str, Any]:
    """Handler for ``enterprise_knowledge_query``. Runs the RAG CLI, returns JSON."""
    if not user_id or not question:
        return {
            "success": False,
            "error": "Both 'user_id' and 'question' are required.",
            "output": None,
        }
    cmd = build_query_cmd(user_id, question, synthesize, k, department, mode)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "enterprise_knowledge query timed out (backing service may be down).",
            "output": None,
        }
    if proc.returncode != 0:
        return {
            "success": False,
            "error": (proc.stderr or proc.stdout or "query failed").strip(),
            "output": None,
        }
    # Return the raw JSON string (not a parsed dict). The react loop's tool-result
    # handling and the compactor's token counter expect string content — exactly
    # like the builtin tools' stdout. A dict here raises "expected string or
    # buffer" in the compactor and the whole turn errors out with no answer.
    return {"success": True, "output": proc.stdout.strip(), "error": None}


def register(ctx: SkillToolContext) -> list[ToolSpec]:
    """Return the enterprise_knowledge agent tools."""
    return [
        ToolSpec(
            name="enterprise_knowledge_query",
            description=(
                "Answer an internal enterprise-knowledge question (company policy, HR, "
                "finance, product, engineering, operations, legal) for a specific user via "
                "permission-aware RAG. Returns cited, permission-filtered results in "
                "Vietnamese. Use this tool for such questions instead of running "
                "knowledge.py by hand. A user_id is REQUIRED (it sets the RBAC scope); "
                "answer only from the returned hits and cite them. EXCEPTION: if the user "
                "explicitly asks for 'grep mode' (dùng grep), do NOT use this tool — follow "
                "the module's grep-mode runbook (search + read_file over the files) instead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Querying user's id — sets the RBAC scope (e.g. U001).",
                    },
                    "question": {
                        "type": "string",
                        "description": "The question, in Vietnamese.",
                    },
                    "synthesize": {
                        "type": "boolean",
                        "description": "Compose a cited Vietnamese answer from the hits.",
                        "default": True,
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of hits to retrieve (default 5).",
                        "default": 5,
                    },
                    "department": {
                        "type": "string",
                        "description": "Optional narrowing within the user's accessible scope.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": list(_VALID_MODES),
                        "description": "Retrieval signal: dense, bm25, or hybrid (default).",
                        "default": "hybrid",
                    },
                },
                "required": ["user_id", "question"],
            },
            handler=_run_query,
        )
    ]
