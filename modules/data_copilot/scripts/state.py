"""AgentState — shared state passed between LangGraph nodes.

Ported from .reference/data-agent/langgraph_agent/state.py. Adds ``executed_cells``:
the reference keeps its process (and Jupyter kernel) alive across the human-review
interrupt, but this CLI does not — on ``resume`` a fresh kernel replays these cells
to rebuild state before continuing.
"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Conversation
    messages: list[dict]
    user_task: str
    # Planner & HITL
    analysis_plan: str
    review_status: str          # "APPROVE" | "REJECT" | "CLARIFICATION"
    review_feedback: str
    review_history: list[dict]
    # Code execution
    generated_code: str
    critic_verdict: bool
    exe_result: str
    exe_sign: str               # "text" | "error"
    executed_cells: list[str]   # ordered cells for kernel replay on resume
    # Retry counters
    syntax_attempts: int
    semantic_attempts: int
    # Verifier
    verdict: dict
    inspector_hypotheses: str
    # Output
    final_report: str
    error_message: str
    # Options threaded from the CLI
    domain: str
    k: Any
    # Run bookkeeping persisted so `resume` can rebuild ctx (dataset, kernel dir)
    # from the checkpoint alone — the CLI only takes --thread/--feedback.
    dataset: str
    run_dir: str
