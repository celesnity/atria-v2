"""Resolve {{ nodes.<key>.output.<field> }} and {{ inputs.<field> }} expressions."""
from __future__ import annotations

import re
from typing import Any

_EXPR = re.compile(r"\{\{\s*(.+?)\s*\}\}")


def _get_nested(data: Any, path: str) -> Any:
    cur = data
    for token in path.split("."):
        if not isinstance(cur, dict):
            raise KeyError(token)
        cur = cur[token]
    return cur


def _eval(expr: str, ctx: dict[str, Any]) -> Any:
    root, _, rest = expr.partition(".")
    if root == "nodes":
        key, _, tail = rest.partition(".")
        node = ctx["nodes"].get(key)
        if node is None:
            raise KeyError(key)
        if tail in ("", "output"):
            return node
        if not tail.startswith("output."):
            raise KeyError(tail)
        return _get_nested(node, tail[len("output."):])
    if root == "inputs":
        return ctx["inputs"] if not rest else _get_nested(ctx["inputs"], rest)
    raise KeyError(root)


def resolve_value(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: resolve_value(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_value(v, ctx) for v in value]
    if not isinstance(value, str):
        return value
    matches = list(_EXPR.finditer(value))
    if not matches:
        return value
    if len(matches) == 1 and matches[0].group(0) == value.strip():
        try:
            return _eval(matches[0].group(1).strip(), ctx)
        except (KeyError, TypeError):
            return value
    out = value
    for m in reversed(matches):
        try:
            sub = str(_eval(m.group(1).strip(), ctx))
        except (KeyError, TypeError):
            continue
        out = out[: m.start()] + sub + out[m.end():]
    return out


def resolve(value: Any, node_outputs: dict[str, dict], inputs: dict) -> Any:
    return resolve_value(value, {"nodes": node_outputs, "inputs": inputs})
