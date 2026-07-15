"""Tool-layer enforcement of protected paths (e.g. RAG corpora).

Some directories must never be touched by agent tools — reading a RAG corpus
directly bypasses retrieval, citations, and guardrails. Prompt-level rules
alone do not survive tool failures, so this guard denies the call at the
single registry dispatch point with a message that redirects the model to the
sanctioned tool.

Scope note: this is behavioral steering with teeth, not adversarial
containment — indirection through arbitrary code execution (``python -c``,
symlinks) can evade the bash text check. The goal is stopping the model's
default fallback behavior. MCP tools return before the registry guard runs
(accepted gap; corpus reads use builtin tools).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional, Sequence

from minder.models.config import ProtectedPath, _default_protected_paths

logger = logging.getLogger(__name__)

_GENERIC_MESSAGE = (
    "Access denied: this path is protected by permissions.protected_paths and "
    "cannot be accessed by tools. Report this to the user instead of trying "
    "alternative access methods."
)

# Tool → path-bearing params checked against protected roots. `path` (used by
# list_files/search) is deliberately absent from param_normalizer._PATH_PARAMS,
# so the guard resolves it itself.
PROTECTED_PATH_PARAMS: dict[str, tuple[str, ...]] = {
    "read_pdf": ("file_path",),
    "notebook_edit": ("notebook_path",),
    # Corpus integrity: writes are denied too.
}

# Tool → free-text params (command lines, glob patterns) checked by substring.
PROTECTED_TEXT_PARAMS: dict[str, tuple[str, ...]] = {
    "run_command": ("command",),
}


class ProtectedPathGuard:
    """Deny tool access to configured protected roots.

    Roots are declared as globs (e.g. ``modules/<name>/<corpus-dir>``) and
    expanded at construction against both the working directory and the modules
    root, so protection holds regardless of which base the agent addresses files
    from.
    """

    def __init__(
        self,
        entries: Optional[Sequence[ProtectedPath]],
        working_dir: Optional[str],
        modules_root: Optional[Path],
    ) -> None:
        self._working_dir = working_dir
        safe_entries = self._sanitize_entries(entries)
        self._roots: list[tuple[Path, str]] = []
        self._needles: list[tuple[str, str]] = []
        bases: list[Path] = []
        if working_dir:
            bases.append(Path(working_dir))
        if modules_root is not None:
            # Patterns are written relative to the repo/deploy root (the
            # modules root's parent), e.g. "modules/<name>/<corpus-dir>".
            bases.append(modules_root.parent)
        for entry in safe_entries:
            message = entry.message or _GENERIC_MESSAGE
            for root in self._expand(entry.pattern, bases):
                self._roots.append((root, message))
                self._needles.append((root.as_posix().lower(), message))
                self._needles.append((root.name.lower(), message))

    @property
    def roots(self) -> list[Path]:
        """The resolved protected root directories."""
        return [root for root, _ in self._roots]

    @staticmethod
    def _sanitize_entries(entries: Optional[Sequence[ProtectedPath]]) -> list[ProtectedPath]:
        """Return valid entries, falling back to built-in defaults.

        Defensive by design: enforcement must survive a missing settings file,
        a mocked config in tests, or a malformed entry.
        """
        fallback: list[ProtectedPath] = _default_protected_paths()
        if not isinstance(entries, (list, tuple)):
            return fallback
        valid = [e for e in entries if isinstance(e, ProtectedPath)]
        return valid if valid else fallback

    @staticmethod
    def _expand(pattern: str, bases: list[Path]) -> list[Path]:
        """Expand a glob pattern into existing directories under the bases."""
        expanded = os.path.expanduser(pattern)
        roots: set[Path] = set()
        if os.path.isabs(expanded):
            candidate = Path(os.path.normpath(expanded))
            if candidate.exists():
                roots.add(candidate)
            return sorted(roots)
        for base in bases:
            try:
                for match in base.glob(expanded):
                    roots.add(Path(os.path.normpath(str(match))))
            except (OSError, ValueError):  # unreadable base or bad pattern
                continue
        return sorted(roots)

    def check_path(self, raw_path: str) -> Optional[str]:
        """Return a denial message when ``raw_path`` is under a protected root."""
        if not raw_path or not self._roots:
            return None
        expanded = os.path.expanduser(raw_path)
        if not os.path.isabs(expanded):
            base = self._working_dir or str(Path.cwd())
            expanded = str(Path(base) / expanded)
        resolved = os.path.normcase(os.path.normpath(expanded))
        resolved_parts = Path(resolved).parts
        for root, message in self._roots:
            root_parts = Path(os.path.normcase(str(root))).parts
            if resolved_parts[: len(root_parts)] == root_parts:
                return message
        return None

    def check_text(self, text: str) -> Optional[str]:
        """Return a denial message when ``text`` references a protected root.

        Used for bash command lines and glob-pattern arguments. Substring
        matching over slash-normalized, lowercased text — deliberately coarse:
        a false denial costs a retry with the sanctioned tool, a false pass
        leaks the corpus.
        """
        if not text or not self._needles:
            return None
        haystack = text.replace("\\", "/").lower()
        for needle, message in self._needles:
            if needle and needle in haystack:
                return message
        return None

    def check_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> Optional[str]:
        """Check one normalized tool call; return a denial message or None."""
        for param in PROTECTED_PATH_PARAMS.get(tool_name, ()):
            value = arguments.get(param)
            if isinstance(value, str) and value:
                denial = self.check_path(value)
                if denial:
                    logger.info("protected-path denial: %s(%s=%r)", tool_name, param, value)
                    return denial
        for param in PROTECTED_TEXT_PARAMS.get(tool_name, ()):
            value = arguments.get(param)
            if isinstance(value, str) and value:
                denial = self.check_text(value)
                if denial:
                    logger.info("protected-path denial: %s(%s=%r)", tool_name, param, value)
                    return denial
        return None
