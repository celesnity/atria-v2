"""Execute generated analysis code as a bounded local subprocess.

Atria already runs inside a sandbox, so this adds process-level bounds rather
than container isolation: a wall-clock timeout, an output-size cap, and a cwd
scoped to a per-run directory into which figures are written.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".svg")
_TRUNCATION_NOTICE = "\n...[truncated]..."

# Env vars the child interpreter genuinely needs to start and to run
# pandas/numpy/sklearn/matplotlib. Everything else — crucially the LLM API keys
# (OPENAI_API_KEY, OPENROUTER_API_KEY, ATRIA_*, DC_*) that are live in the parent
# during `analyze` — is withheld so generated code cannot read a secret and print
# it into stdout (which is captured and fed into the report). Prefix matches cover
# the loader families (LC_*, and Windows' SystemRoot/SYSTEMROOT/windir).
_ENV_ALLOW = frozenset(
    {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "TMPDIR",
        "TMP",
        "TEMP",
        "PYTHONHASHSEED",
        "PYTHONIOENCODING",
        "SYSTEMROOT",
        "SystemRoot",
        "WINDIR",
        "windir",
        "COMSPEC",
        "NUMBER_OF_PROCESSORS",
    }
)
_ENV_ALLOW_PREFIXES = ("LC_",)


def _safe_env() -> Dict[str, str]:
    """Build a minimal environment for the sandboxed child.

    Copies only allow-listed vars from the parent so secrets (API keys) are not
    inherited by LLM-generated code, then forces matplotlib into a headless,
    file-writing mode.
    """
    env = {
        k: v for k, v in os.environ.items() if k in _ENV_ALLOW or k.startswith(_ENV_ALLOW_PREFIXES)
    }
    env["MPLBACKEND"] = "Agg"  # headless plotting regardless of parent config
    return env


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + _TRUNCATION_NOTICE


def run_code(
    code: str,
    workdir: str,
    timeout: float = 30.0,
    max_output: int = 20000,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, object]:
    """Run *code* in *workdir* as a subprocess with bounds.

    Args:
        code: Python source to execute.
        workdir: Directory used as cwd; created if missing. Figures land here.
        timeout: Wall-clock limit in seconds.
        max_output: Max characters kept from each of stdout/stderr.
        env: Environment for the child. Defaults to a scrubbed, secret-free env
            (see :func:`_safe_env`); pass an explicit mapping to override.

    Returns:
        ``{"status", "stdout", "stderr", "figures", "returncode"}`` where
        ``status`` is ``"text"`` on a clean exit (code 0) and ``"error"``
        otherwise. ``figures`` lists image files present after the run.
    """
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    before = {p.name: p.stat().st_mtime for p in wd.iterdir() if p.is_file()}
    script = wd / "_run.py"
    script.write_text(code, encoding="utf-8")
    child_env = _safe_env() if env is None else env

    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(wd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=child_env,
        )
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        return {
            "status": "error",
            "stdout": _cap(stdout, max_output),
            "stderr": f"timeout: execution exceeded {timeout}s",
            "figures": [],
            "returncode": None,
        }

    figures: List[str] = []
    for p in sorted(wd.iterdir()):
        if not p.is_file() or p.suffix.lower() not in _IMAGE_EXTS:
            continue
        prev_mtime = before.get(p.name)
        if prev_mtime is None or p.stat().st_mtime > prev_mtime:
            figures.append(str(p))
    return {
        "status": "text" if rc == 0 else "error",
        "stdout": _cap(stdout, max_output),
        "stderr": _cap(stderr, max_output),
        "figures": figures,
        "returncode": rc,
    }
