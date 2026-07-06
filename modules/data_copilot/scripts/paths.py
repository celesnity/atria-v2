"""Resolve where data_copilot writes its artifacts.

Keyed by the atria session id so the bash-invoked scripts, the agent-side
tools, and the save route all resolve the *same* directory with no DB lookup.
Falls back to the module dir for the bare CLI/TUI (no session in env).
"""

from __future__ import annotations

import os
from pathlib import Path


def _module_dir() -> Path:
    """The module root (``modules/data_copilot``) — the standalone fallback."""
    return Path(__file__).resolve().parent.parent


def conversation_root() -> Path:
    """Session-keyed artifact root, or the module dir when no session in env."""
    workspace = os.environ.get("ATRIA_WORKSPACE") or os.environ.get("ATRIA_SESSION_DIR")
    session = os.environ.get("ATRIA_CONVERSATION_ID")
    if workspace and session:
        return Path(workspace) / ".artifacts" / "data_copilot" / session
    return _module_dir()


def _in_module_fallback() -> bool:
    return conversation_root() == _module_dir()


def data_dir() -> Path:
    """Dir for ingested + derived CSVs (created on access)."""
    d = conversation_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def runs_dir() -> Path:
    """Dir holding per-run output subdirs (created on access)."""
    d = conversation_root() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_run_dir(name: str = "latest") -> Path:
    """Create and return a run output dir under ``runs/`` (fixed name)."""
    d = runs_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_unique_run_dir() -> Path:
    """Create and return a fresh, collision-free run dir under ``runs/``.

    Each ``analyze``/``persona`` invocation gets its own dir so one run's
    ``result.csv`` / figures never overwrite another's. The dir name carries a
    human-readable timestamp plus a random suffix (via ``mkdtemp``) so concurrent
    or same-second runs stay isolated.
    """
    import tempfile
    import time

    base = runs_dir()
    prefix = time.strftime("run-%Y%m%d-%H%M%S-")
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))


def checkpoint_db() -> Path:
    """SQLite path for the LangGraph checkpointer (session-scoped)."""
    return conversation_root() / "graph_checkpoints.sqlite"


def audit_path() -> Path:
    """Audit log path — ``audit.jsonl`` in a session, legacy name in fallback."""
    if _in_module_fallback():
        return _module_dir() / "audit_log.jsonl"
    return conversation_root() / "audit.jsonl"
