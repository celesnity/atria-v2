"""Static pre-execution guardrails for generated analysis code.

Enforced in code, not left to the prompt. The runtime is already sandboxed;
this is a best-effort AST screen that blocks code which reaches out to the
network, spawns processes, escapes the run directory, or does dynamic imports
before it ever runs. Parsing with ``ast`` (rather than regex over source) means
comments and string literals never trigger false positives, and multi-line or
parenthesized import forms cannot slip through.
"""

from __future__ import annotations

import ast
import re
from typing import Dict, List, Optional

_NETWORK_MODULES = {"socket", "requests", "urllib", "http", "httpx", "aiohttp",
                    "ftplib", "smtplib"}
_PROCESS_MODULES = {"subprocess", "multiprocessing"}
_OS_EXEC_FUNCS = {"system", "popen"}
_OS_DELETE_FUNCS = {"remove", "unlink"}
_DYNAMIC_CALLS = {"eval", "exec", "__import__"}
_ABS_OR_PARENT_RE = re.compile(r"^(/|\.\.|[a-zA-Z]:\\)")

_NETWORK_REASON = "network access is not allowed"
_PROCESS_REASON = "spawning processes is not allowed"
_SHELL_REASON = "shell/process execution is not allowed"
_DELETE_REASON = "file deletion is not allowed"
_RMTREE_REASON = "recursive delete is not allowed"
_DYNAMIC_REASON = "dynamic eval/exec/__import__ is not allowed"
_WRITE_REASON = "writing outside the run directory is not allowed"


def _root(module: Optional[str]) -> str:
    """Return the top-level package of a dotted module name."""
    return (module or "").split(".")[0]


def _is_os_exec(attr: str) -> bool:
    """True for os functions that spawn a shell/process (system/popen/exec*/spawn*)."""
    return attr in _OS_EXEC_FUNCS or attr.startswith("exec") or attr.startswith(
        "spawn")


def _str_prefix(node: ast.AST) -> Optional[str]:
    """Return a string literal, or the leading literal chunk of an f-string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values:
        first = node.values[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def _is_write_mode(mode: str) -> bool:
    """True when an open() mode string requests write/append/create."""
    return any(c in mode for c in "wax+")


def _open_writes_outside(call: ast.Call) -> bool:
    """True when an ``open()`` call writes/appends to an absolute or parent path."""
    path_node = call.args[0] if call.args else None
    mode_node = call.args[1] if len(call.args) > 1 else None
    for kw in call.keywords:
        if kw.arg == "file":
            path_node = kw.value
        elif kw.arg == "mode":
            mode_node = kw.value
    if path_node is None:
        return False
    prefix = _str_prefix(path_node)
    if prefix is None or not _ABS_OR_PARENT_RE.match(prefix):
        return False
    if mode_node is None:
        return False  # default mode is read
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return _is_write_mode(mode_node.value)
    return True  # non-literal mode on an abs/parent path: treat as unsafe


def check_code(code: str) -> Dict[str, object]:
    """Statically screen generated code for disallowed operations.

    Parses *code* into an AST and inspects imports and calls. Code that fails to
    parse is allowed through — it cannot execute, so the sandbox will simply
    surface the SyntaxError to the repair loop.

    Args:
        code: The Python source to screen.

    Returns:
        ``{"allowed": bool, "reasons": list[str]}`` — ``allowed`` is ``False``
        when any rule matches; ``reasons`` lists distinct triggered reasons in
        first-seen order.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"allowed": True, "reasons": []}

    reasons: List[str] = []

    def add(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    # Resolve local names bound to os/shutil (incl. aliases) so attribute-call
    # checks catch `import os as o; o.system(...)`.
    aliased: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _root(alias.name)
                if root in ("os", "shutil"):
                    local = (alias.asname or alias.name).split(".")[0]
                    aliased[local] = root

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _root(alias.name)
                if root in _NETWORK_MODULES:
                    add(_NETWORK_REASON)
                if root in _PROCESS_MODULES:
                    add(_PROCESS_REASON)
        elif isinstance(node, ast.ImportFrom):
            root = _root(node.module)
            if root in _NETWORK_MODULES:
                add(_NETWORK_REASON)
            if root in _PROCESS_MODULES:
                add(_PROCESS_REASON)
            if root == "os":
                for alias in node.names:
                    if _is_os_exec(alias.name):
                        add(_SHELL_REASON)
                    if alias.name in _OS_DELETE_FUNCS:
                        add(_DELETE_REASON)
            if root == "shutil":
                for alias in node.names:
                    if alias.name == "rmtree":
                        add(_RMTREE_REASON)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in _DYNAMIC_CALLS:
                    add(_DYNAMIC_REASON)
                elif func.id == "open" and _open_writes_outside(node):
                    add(_WRITE_REASON)
            elif isinstance(func, ast.Attribute):
                base = func.value
                base_name = base.id if isinstance(base, ast.Name) else None
                canonical = aliased.get(base_name, base_name)
                if canonical == "os":
                    if _is_os_exec(func.attr):
                        add(_SHELL_REASON)
                    if func.attr in _OS_DELETE_FUNCS:
                        add(_DELETE_REASON)
                elif canonical == "shutil" and func.attr == "rmtree":
                    add(_RMTREE_REASON)

    return {"allowed": not reasons, "reasons": reasons}
