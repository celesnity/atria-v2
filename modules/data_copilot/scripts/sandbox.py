"""Execute generated analysis code as a bounded local subprocess.

Atria already runs inside a sandbox, so this adds process-level bounds rather
than container isolation: a wall-clock timeout, an output-size cap, and a cwd
scoped to a per-run directory into which figures are written.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Dict, List

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".svg")
_TRUNCATION_NOTICE = "\n...[truncated]..."


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + _TRUNCATION_NOTICE


def run_code(
    code: str,
    workdir: str,
    timeout: float = 30.0,
    max_output: int = 20000,
) -> Dict[str, object]:
    """Run *code* in *workdir* as a subprocess with bounds.

    Args:
        code: Python source to execute.
        workdir: Directory used as cwd; created if missing. Figures land here.
        timeout: Wall-clock limit in seconds.
        max_output: Max characters kept from each of stdout/stderr.

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

    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(wd),
            capture_output=True,
            text=True,
            timeout=timeout,
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
