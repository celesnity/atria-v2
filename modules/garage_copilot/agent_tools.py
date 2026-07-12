"""Agent-callable tool for garage_copilot: cited workshop-manual RAG query.

Exposes ``garage_copilot_query`` so the model calls a typed tool instead of
hand-composing a ``python garage.py query ...`` shell command (the same
lesson enterprise_knowledge learned: a structured tool removes the shell
surface entirely). garage v1 has no RBAC — the corpus is open to every
technician — so the tool takes only the question and retrieval knobs.

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
_GARAGE = _SCRIPTS / "garage.py"
_WORKLOG = _SCRIPTS / "worklog.py"

_VALID_MODES = ("dense", "bm25", "hybrid")


def build_query_cmd(
    question: str,
    synthesize: bool = False,
    k: int = 5,
    mode: str = "hybrid",
) -> list[str]:
    """Build the exact ``garage.py query`` argv. Pure — unit-testable.

    Uses an absolute path to ``garage.py`` so it works regardless of the
    caller's working directory. ``synthesize`` defaults to False for the
    agent path: the synthesis pass costs a full extra LLM generation
    (~6-12 s) that the main agent would only re-write — the agent composes
    its own streamed answer from the raw hits instead. The CLI keeps
    ``--synthesize`` for human/API use.
    """
    if mode not in _VALID_MODES:
        mode = "hybrid"
    cmd = [
        sys.executable,
        str(_GARAGE),
        "query",
        str(question),
        "--k",
        str(int(k)),
        "--mode",
        str(mode),
    ]
    if synthesize:
        cmd.append("--synthesize")
    return cmd


def _run_query(
    question: str = "",
    synthesize: bool = False,
    k: int = 5,
    mode: str = "hybrid",
    **_ignored: Any,
) -> dict[str, Any]:
    """Handler for ``garage_copilot_query``. Runs the RAG CLI, returns JSON."""
    if not question:
        return {
            "success": False,
            "error": "'question' is required.",
            "output": None,
        }
    cmd = build_query_cmd(question, synthesize, k, mode)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "garage_copilot query timed out (backing service may be down).",
            "output": None,
        }
    if proc.returncode != 0:
        return {
            "success": False,
            "error": (proc.stderr or proc.stdout or "query failed").strip(),
            "output": None,
        }
    # Raw JSON string, not a parsed dict — the react loop's tool-result handling
    # and the compactor's token counter expect string content.
    return {"success": True, "output": proc.stdout.strip(), "error": None}


def build_worklog_search_cmd(
    query: str,
    k: int = 5,
    vin: str | None = None,
    brand: str | None = None,
) -> list[str]:
    """Build the exact ``worklog.py search`` argv. Pure — unit-testable."""
    cmd = [sys.executable, str(_WORKLOG), "search", str(query), "--k", str(int(k))]
    if vin:
        cmd += ["--vin", str(vin)]
    if brand:
        cmd += ["--brand", str(brand)]
    return cmd


def _run_worklog_search(
    query: str = "",
    k: int = 5,
    vin: str | None = None,
    brand: str | None = None,
    **_ignored: Any,
) -> dict[str, Any]:
    """Handler for ``work_log_search``. Runs the worklog CLI, returns JSON."""
    if not query:
        return {"success": False, "error": "'query' is required.", "output": None}
    cmd = build_worklog_search_cmd(query, k, vin, brand)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "work_log_search timed out (backing service may be down).",
            "output": None,
        }
    if proc.returncode != 0:
        return {
            "success": False,
            "error": (proc.stderr or proc.stdout or "search failed").strip(),
            "output": None,
        }
    return {"success": True, "output": proc.stdout.strip(), "error": None}


def register(ctx: SkillToolContext) -> list[ToolSpec]:
    """Return the garage_copilot agent tools."""
    return [
        ToolSpec(
            name="garage_copilot_query",
            description=(
                "Retrieve the most relevant workshop-manual passages (Rolls-Royce, "
                "Lamborghini, McLaren service content) for a vehicle-repair knowledge "
                "question. Use this for every repair/diagnostic knowledge lookup instead "
                "of answering from your own knowledge. Returns ranked hits, each with "
                "the passage text and a chunk_id like WSM-RR-2040#1 — compose your answer "
                "from the hit texts and cite every grounded claim with its [chunk_id]. "
                "Query in English for best retrieval (translate the technician's "
                "Vietnamese internally). If this tool reports an outage, say the "
                "knowledge service is down; never substitute uncited knowledge silently."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The repair-knowledge question, in English.",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of passages to retrieve (default 5).",
                        "default": 5,
                    },
                    "mode": {
                        "type": "string",
                        "enum": list(_VALID_MODES),
                        "description": "Retrieval signal: dense, bm25, or hybrid (default).",
                        "default": "hybrid",
                    },
                },
                "required": ["question"],
            },
            handler=_run_query,
        ),
        ToolSpec(
            name="work_log_search",
            description=(
                "Search past repair work logs of this workshop by symptom, cause, or fix "
                "(paraphrase-tolerant). Use when a symptom sounds familiar — a problem "
                "solved once here should never be re-diagnosed from scratch. Returns "
                "structured records (symptom as reported, hypotheses tried incl. dead "
                "ends, root cause, fix, parts) with their RO/VIN/brand. Query in "
                "Vietnamese or English; optionally filter by exact VIN or brand."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Symptom/cause/fix to search for (VI or EN).",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Max results (default 5).",
                        "default": 5,
                    },
                    "vin": {
                        "type": "string",
                        "description": "Exact VIN filter (this vehicle's history).",
                    },
                    "brand": {
                        "type": "string",
                        "description": "Brand filter: Rolls-Royce, Lamborghini, McLaren.",
                    },
                },
                "required": ["query"],
            },
            handler=_run_worklog_search,
        ),
    ]
