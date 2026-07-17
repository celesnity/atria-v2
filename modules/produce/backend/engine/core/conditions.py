"""Single-condition evaluator ported from the reference ifelse node."""
from __future__ import annotations

from typing import Any

_CMP = ("==", "!=", ">", "<", ">=", "<=")
_STR = ("contains", "not_contains", "is_empty", "is_not_empty")


def _coerce(left: Any, right: Any) -> tuple[Any, Any]:
    if isinstance(left, str) and isinstance(right, (int, float)):
        try:
            left = type(right)(left)
        except (ValueError, TypeError):
            pass
    elif isinstance(right, str) and isinstance(left, (int, float)):
        try:
            right = type(left)(right)
        except (ValueError, TypeError):
            pass
    return left, right


def evaluate_condition(cond: dict[str, Any]) -> bool:
    left, op, right = cond.get("left"), cond.get("operator", ""), cond.get("right")
    if op not in _CMP + _STR:
        return False
    if op == "is_empty":
        return left is None or (isinstance(left, str) and left.strip() == "")
    if op == "is_not_empty":
        return left is not None and not (isinstance(left, str) and left.strip() == "")
    if op == "contains":
        return isinstance(left, str) and isinstance(right, str) and right in left
    if op == "not_contains":
        return isinstance(left, str) and isinstance(right, str) and right not in left
    left, right = _coerce(left, right)
    try:
        return {
            "==": left == right, "!=": left != right,
            ">": left > right, "<": left < right,
            ">=": left >= right, "<=": left <= right,
        }[op]
    except TypeError:
        return False
