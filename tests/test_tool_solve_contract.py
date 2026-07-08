"""Guard the solve-tool behavioral contract text against silent regression."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_TOOL_MD = _ROOT / "atria" / "core" / "agents" / "prompts" / "templates" / "tools" / "tool-solve.md"
_SCHEMA = (
    _ROOT
    / "atria"
    / "core"
    / "agents"
    / "components"
    / "schemas"
    / "builtin"
    / "orchestration_tools.py"
)


def test_tool_solve_md_forbids_trivial_dispatch() -> None:
    text = _TOOL_MD.read_text(encoding="utf-8")
    assert "Do NOT dispatch single-step" in text
    assert "answer them directly with normal tools" in text


def test_tool_solve_md_mandates_collect_and_answer() -> None:
    text = _TOOL_MD.read_text(encoding="utf-8")
    assert "Dispatch is not an answer" in text
    assert "get_solve_result" in text and "block=true" in text


def test_schema_strategy_description_carries_contract() -> None:
    text = _SCHEMA.read_text(encoding="utf-8")
    assert "you must then call get_solve_result" in text
