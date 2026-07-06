"""LangGraph assembly for data_copilot. Mirrors
.reference/data-agent/langgraph_agent/graph.py: same nodes, same conditional
edges, same retry budgets (syntax 4, semantic 5). Nodes are bound to a ctx via
functools.partial so they stay pure.
"""

from __future__ import annotations

from functools import partial
from typing import Any, Dict

from langgraph.graph import END, StateGraph  # type: ignore[import-not-found]

import nodes  # type: ignore[import-not-found]
from state import AgentState  # type: ignore[import-not-found]

SYNTAX_MAX = 4
SEMANTIC_MAX = 5


def _after_classify(state: Dict[str, Any]) -> str:
    """Route after classify_review: retry the plan unless the human approved it."""
    return "generate_code" if state.get("review_status") == "APPROVE" else "generate_plan"


def _after_critic(state: Dict[str, Any]) -> str:
    """Route after code_critic: execute on pass, else regenerate the code."""
    return "execute_code" if state.get("critic_verdict") else "generate_code"


def _after_execute(state: Dict[str, Any]) -> str:
    """Route after execute_code: verify semantics, repair, or give up on budget."""
    sign = state.get("exe_sign", "")
    if sign and "error" not in sign:
        return "semantic_verify"
    if state.get("syntax_attempts", 0) >= SYNTAX_MAX:
        return "generate_report"
    return "repair_code"


def _after_verify(state: Dict[str, Any]) -> str:
    """Route after semantic_verify: accept, or request a fix within budget."""
    verdict = state.get("verdict", {})
    if verdict.get("status") == "ACCEPT" or state.get("semantic_attempts", 0) >= SEMANTIC_MAX:
        return "generate_report"
    return "semantic_fix"


def build_graph(ctx: Any, checkpointer: Any):
    """Assemble and compile the data_copilot StateGraph.

    Args:
        ctx: Namespace carrying shared services (``rc``, ``kernel``, etc.) that
            get bound into every node via ``functools.partial``.
        checkpointer: A LangGraph checkpointer (e.g. ``MemorySaver`` or
            ``SqliteSaver``) used to persist state across the human-review
            interrupt.

    Returns:
        The compiled ``CompiledGraph``.
    """
    g = StateGraph(AgentState)
    for name in (
        "generate_plan",
        "human_review",
        "classify_review",
        "generate_code",
        "code_critic",
        "execute_code",
        "repair_code",
        "semantic_verify",
        "semantic_fix",
        "generate_report",
    ):
        g.add_node(name, partial(getattr(nodes, name), ctx=ctx))

    g.set_entry_point("generate_plan")
    g.add_edge("generate_plan", "human_review")
    g.add_edge("human_review", "classify_review")
    g.add_conditional_edges(
        "classify_review",
        _after_classify,
        {"generate_code": "generate_code", "generate_plan": "generate_plan"},
    )
    g.add_edge("generate_code", "code_critic")
    g.add_conditional_edges(
        "code_critic",
        _after_critic,
        {"execute_code": "execute_code", "generate_code": "generate_code"},
    )
    g.add_conditional_edges(
        "execute_code",
        _after_execute,
        {
            "repair_code": "repair_code",
            "semantic_verify": "semantic_verify",
            "generate_report": "generate_report",
        },
    )
    g.add_edge("repair_code", "execute_code")
    g.add_conditional_edges(
        "semantic_verify",
        _after_verify,
        {"generate_report": "generate_report", "semantic_fix": "semantic_fix"},
    )
    g.add_edge("semantic_fix", "execute_code")
    g.add_edge("generate_report", END)

    return g.compile(checkpointer=checkpointer)
