"""LangGraph nodes for data_copilot. Adapted from
.reference/data-agent/langgraph_agent/nodes.py: pure (state, ctx) -> partial-state
functions. LLM calls bind to ctx.rc (RoleClient, non-streaming); code runs on
ctx.kernel (stateful). No chat_history_display — progress is emitted by the graph
driver to stderr.
"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.types import interrupt  # type: ignore[import-not-found]

import gates  # type: ignore[import-not-found]
import prompts  # type: ignore[import-not-found]
import report_generator  # type: ignore[import-not-found]
from generate import extract_code  # type: ignore[import-not-found]
from guardrails import check_code  # type: ignore[import-not-found]


def generate_plan(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    """Ask the codegen role to produce an Analysis Plan for the user's task.

    Args:
        state: Graph state; reads ``user_task`` and optional ``review_feedback``.
        ctx: Namespace carrying ``rc`` (RoleClient).

    Returns:
        Partial state with the new ``analysis_plan``.
    """
    prompt = prompts.PLANNER_PROMPT + f"\n\nUser Task: {state.get('user_task', '')}"
    if state.get("review_feedback"):
        prompt += (
            f"\n\nHuman Review Feedback: {state['review_feedback']}\nRevise the plan accordingly."
        )
    plan = ctx.rc.chat("codegen", [{"role": "user", "content": prompt}])
    return {"analysis_plan": plan}


def human_review(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    """Pause graph execution to collect human feedback on the analysis plan.

    Args:
        state: Graph state; reads ``analysis_plan``.
        ctx: Unused; kept for signature consistency with other nodes.

    Returns:
        Partial state with ``review_feedback`` set to the resumed decision.
    """
    decision = interrupt({"type": "plan_review", "plan": state.get("analysis_plan", "")})
    return {"review_feedback": decision}


def classify_review(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    """Classify human review feedback into APPROVE, CLARIFICATION, or REJECT.

    Args:
        state: Graph state; reads ``review_feedback`` and ``review_history``.
        ctx: Namespace carrying ``rc`` (RoleClient).

    Returns:
        Partial state with ``review_status`` and the appended ``review_history``.
    """
    prompt = prompts.CLASSIFIER_PROMPT.format(feedback=state.get("review_feedback", ""))
    resp = ctx.rc.chat("codegen", [{"role": "user", "content": prompt}]).upper()
    if "APPROVE" in resp:
        status = "APPROVE"
    elif "CLARIFICATION" in resp:
        status = "CLARIFICATION"
    else:
        status = "REJECT"
    history = state.get("review_history", [])
    history.append(
        {
            "version": len(history) + 1,
            "feedback": state.get("review_feedback", ""),
            "status": status,
        }
    )
    return {"review_status": status, "review_history": history}


def generate_code(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    """Ask the codegen role to write Python code implementing the analysis plan.

    Args:
        state: Graph state; reads ``critic_verdict``, ``error_message``, and
            ``analysis_plan``.
        ctx: Namespace carrying ``rc`` (RoleClient).

    Returns:
        Partial state with the new ``generated_code``.
    """
    if state.get("critic_verdict") is False:
        msg = (
            f"The Code Critic rejected your code. Reason: {state.get('error_message', '')}\n"
            "Write a corrected Python script based on the analysis plan."
        )
    else:
        msg = (
            "Generate the complete Python code to implement this plan:\n\n"
            f"{state.get('analysis_plan', '')}"
        )
    text = ctx.rc.chat(
        "codegen",
        [
            {"role": "system", "content": prompts.PROGRAMMER_PROMPT},
            {"role": "user", "content": msg},
        ],
    )
    _, code = extract_code(text)
    return {"generated_code": code or text}


def code_critic(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    """Quality gate for generated code, run by the codegen role before execution.

    Args:
        state: Graph state; reads ``generated_code``.
        ctx: Namespace carrying ``rc`` (RoleClient).

    Returns:
        Partial state with ``critic_verdict`` (bool) and ``error_message``.
    """
    resp = ctx.rc.chat(
        "codegen",
        [
            {
                "role": "user",
                "content": prompts.CRITIC_PROMPT.format(code=state.get("generated_code", "")),
            }
        ],
    )
    if "FAIL" in resp.upper():
        return {"critic_verdict": False, "error_message": resp.replace("FAIL", "").strip()}
    return {"critic_verdict": True, "error_message": ""}


def execute_code(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    """Screen and run the generated code in the stateful kernel.

    Args:
        state: Graph state; reads ``generated_code`` and ``executed_cells``.
        ctx: Namespace carrying ``kernel`` (CodeKernel).

    Returns:
        Partial state with ``exe_sign``, ``exe_result``, ``executed_cells`` (with
        the code appended on success), and ``figures``.
    """
    code = state.get("generated_code", "")
    if not code:
        return {
            "exe_sign": "error",
            "exe_result": "No code to execute.",
            "error_message": "Empty code block.",
        }
    guard = check_code(code)
    if not guard["allowed"]:
        return {"exe_sign": "error", "exe_result": "GUARDRAIL: " + "; ".join(guard["reasons"])}
    res = ctx.kernel.run(code)
    cells = state.get("executed_cells", [])
    if res["status"] != "error":
        cells = cells + [code]
    return {
        "exe_sign": res["status"],
        "exe_result": res["stdout"],
        "executed_cells": cells,
        "figures": res.get("figures", []),
    }


def repair_code(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    """Diagnose an execution error and ask the codegen role for an incremental fix.

    Args:
        state: Graph state; reads ``syntax_attempts``, ``generated_code``,
            ``exe_result``, and ``user_task``.
        ctx: Namespace carrying ``rc`` (RoleClient).

    Returns:
        Partial state with the repaired ``generated_code``, incremented
        ``syntax_attempts``, and the diagnostic ``inspector_hypotheses``.
    """
    attempts = state.get("syntax_attempts", 0)
    hyp = (
        gates.verify_syntax(
            state.get("generated_code", ""),
            state.get("exe_result", ""),
            state.get("user_task", ""),
            lambda m: ctx.rc.chat("verify", m),
        )
        if attempts < 3
        else "Try other packages or methods."
    )
    fix_msg = (
        f"Fix this bug:\n{state.get('exe_result', '')}\n\nSuggestion: {hyp}\n\n"
        "INCREMENTAL FIX: change only the lines needed; the kernel is stateful."
    )
    text = ctx.rc.chat(
        "codegen",
        [
            {"role": "system", "content": prompts.PROGRAMMER_PROMPT},
            {"role": "user", "content": fix_msg},
        ],
    )
    _, new_code = extract_code(text)
    return {
        "generated_code": new_code or state.get("generated_code", ""),
        "syntax_attempts": attempts + 1,
        "inspector_hypotheses": hyp,
    }


def semantic_verify(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    """Run the semantic gates on the code's execution output.

    Args:
        state: Graph state; reads ``user_task``, ``generated_code``, and
            ``exe_result``.
        ctx: Namespace carrying an optional ``domain`` hint.

    Returns:
        Partial state with the ``verdict`` dict and current ``semantic_attempts``.
    """
    v = gates.verify_semantics(
        state.get("user_task", ""),
        state.get("generated_code", ""),
        state.get("exe_result", ""),
        domain=getattr(ctx, "domain", None),
    )
    return {"verdict": v, "semantic_attempts": state.get("semantic_attempts", 0)}


def semantic_fix(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    """Apply semantic-verifier feedback and re-generate the code.

    Args:
        state: Graph state; reads ``verdict`` and ``semantic_attempts``.
        ctx: Namespace carrying ``rc`` (RoleClient).

    Returns:
        Partial state with the revised ``generated_code`` and incremented
        ``semantic_attempts``.
    """
    fb = state.get("verdict", {}).get("feedback", "")
    text = ctx.rc.chat(
        "codegen",
        [
            {"role": "system", "content": prompts.PROGRAMMER_PROMPT},
            {"role": "user", "content": prompts.SEMANTIC_FIX.format(feedback=fb)},
        ],
    )
    _, new_code = extract_code(text)
    return {
        "generated_code": new_code or state.get("generated_code", ""),
        "semantic_attempts": state.get("semantic_attempts", 0) + 1,
    }


def generate_report(state: Dict[str, Any], ctx) -> Dict[str, Any]:
    """Compose the final business report from the execution output.

    Args:
        state: Graph state; reads ``exe_result``, ``exe_sign``, ``error_message``,
            and ``user_task``.
        ctx: Namespace carrying ``rc`` (RoleClient).

    Returns:
        Partial state with the ``final_report`` markdown text.
    """
    out = state.get("exe_result", "")
    if state.get("exe_sign") == "error":
        out = (out + "\n\n[execution error]\n" + state.get("error_message", "")).strip()
    report = report_generator.compose(out, rc=ctx.rc, question=state.get("user_task", ""))
    return {"final_report": report}
