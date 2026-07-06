"""Stateful IPython kernel executor for generated analysis code.

Adapted from .reference/data-agent/triadic_dgm/sandbox/kernel.py. Unlike the
one-shot subprocess sandbox, this keeps a live kernel so variables persist across
cells (incremental repair). Env is scrubbed exactly like sandbox._safe_env so
LLM-generated code cannot read API keys. Figures written into the workdir are
collected by mtime, mirroring sandbox.run_code.
"""

from __future__ import annotations

import queue
import re
import sys
from pathlib import Path
from typing import Dict, List

import jupyter_client  # type: ignore[import-not-found]

# Ensure the sibling `sandbox` module resolves when this file is loaded directly
# (e.g. via importlib.util.spec_from_file_location in tests) rather than as part
# of a package with this directory already on sys.path. Appended (not prepended)
# so stdlib modules win first — this directory also holds a `profile.py`, which
# would otherwise shadow the stdlib `profile` module that cProfile/IPython import.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.append(_SCRIPTS_DIR)

import sandbox  # type: ignore[import-not-found]  # noqa: E402

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".svg")
_EXEC_TIMEOUT = 30.0


class CodeKernel:
    """A live IPython kernel scoped to a run directory."""

    def __init__(self, workdir: str) -> None:
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        env = sandbox._safe_env()
        self._km = jupyter_client.KernelManager(kernel_name="python3")
        # `env` must be passed to start_kernel (not the constructor): jupyter_client's
        # provisioner defaults to a *copy of the full parent os.environ* when "env" is
        # absent from the start_kernel kwargs, which would silently leak secrets.
        self._km.start_kernel(cwd=str(self.workdir), env=env)
        self._kc = self._km.blocking_client()
        self._kc.start_channels()
        self._kc.wait_for_ready(timeout=60)

    def _drain(self, msg_id: str) -> Dict[str, object]:
        """Collect stdout/errors until the kernel returns to idle."""
        chunks: List[str] = []
        status = "text"
        while True:
            try:
                msg = self._kc.get_iopub_msg(timeout=_EXEC_TIMEOUT)
            except queue.Empty:
                self._km.interrupt_kernel()
                return {
                    "status": "error",
                    "stdout": f"timeout: execution exceeded {_EXEC_TIMEOUT}s",
                }
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            mtype = msg["msg_type"]
            content = msg["content"]
            if mtype == "stream":
                chunks.append(content.get("text", ""))
            elif mtype == "execute_result":
                chunks.append(str(content.get("data", {}).get("text/plain", "")))
            elif mtype == "error":
                status = "error"
                chunks.append("\n".join(content.get("traceback", [])))
            elif mtype == "status" and content.get("execution_state") == "idle":
                break
        # Strip ANSI escape codes from tracebacks for a clean stdout.
        text = re.sub(r"\x1b\[[0-9;]*m", "", "".join(chunks))
        return {"status": status, "stdout": text}

    def run(self, code: str) -> Dict[str, object]:
        """Execute one cell; return {status, stdout, figures}."""
        before = {p.name: p.stat().st_mtime for p in self.workdir.iterdir() if p.is_file()}
        msg_id = self._kc.execute(code)
        out = self._drain(msg_id)
        figures: List[str] = []
        for p in sorted(self.workdir.iterdir()):
            if not p.is_file() or p.suffix.lower() not in _IMAGE_EXTS:
                continue
            prev = before.get(p.name)
            if prev is None or p.stat().st_mtime > prev:
                figures.append(str(p))
        out["figures"] = figures
        return out

    def replay(self, cells: List[str]) -> None:
        """Re-execute prior cells to rebuild kernel state (output ignored)."""
        for cell in cells:
            self._drain(self._kc.execute(cell))

    def shutdown(self) -> None:
        """Stop channels and shut down the kernel process."""
        try:
            self._kc.stop_channels()
        finally:
            self._km.shutdown_kernel(now=True)
