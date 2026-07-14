"""Minder skill for the Optimize console -- the 6-stage operational decision pipeline.

Declared via ``tools: tools.py`` in ``SKILL.md``. ``register(ctx)`` returns agent tools that let the
**core Minder agent** run the manufacturing decision loop as SEPARATE, routable skills -- one per
operational question -- instead of a single general-purpose prompt:

    "What happened?"        -> measure_operational_performance
    "Why did it happen?"    -> explain_performance_loss
    "What will happen?"     -> predict_operational_risk
    "What are the options?" -> evaluate_operational_alternatives
    "What should we do?"    -> recommend_operational_action   (prepares a decision, awaits approval)
    "Apply the decision."   -> replan_and_dispatch_operations (actuates ONLY after human approval)

For a compound ask ("why are we behind and what should we do?") the agent chains them in order,
threading the ``execution_id`` returned by the first stage into the rest so every stage reads ONE
shared live snapshot (coherent numbers). ``optimize_analyze_fleet`` runs the whole loop in one call.

Honest sources: the only system of record is the live IIOT fleet simulator (``/api/fleet/*``) plus
the decision store (``data/*.json``); the professional roles named below are analogies. Numbers are
never invented -- ``pipeline``/``simulate`` own every figure (incl. confidence + data-quality); the
model only writes the ``summary`` prose, and degrades to a deterministic sentence with no key.
"""

from __future__ import annotations

import json
import os
import sys

# The shared pipeline core + analysis + the live fleet client live under scripts/.
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import analysis  # noqa: E402
import pipeline  # noqa: E402
import simulate  # noqa: E402

try:  # minder is present in the app runtime; guard so the file is importable standalone (tests)
    from minder.core.skill_tools import ToolSpec  # type: ignore
except Exception:  # pragma: no cover - standalone/import-without-minder
    ToolSpec = None  # type: ignore[assignment,misc]


def _llm_fn(ctx):
    """A sync (system, user) -> str callable backed by Minder's model, or None if unavailable."""
    fn = getattr(ctx, "llm_chat", None) if ctx is not None else None
    if not callable(fn):
        return None

    def _call(system: str, user: str) -> str:
        return fn(system, user)

    return _call


def _ok(resp: dict) -> dict:
    """Wrap a pipeline response into the registry's {success, output} contract."""
    return {"success": True, "output": json.dumps(resp, ensure_ascii=False)}


def _stage_handler(ctx, skill: str):
    def handler(
        lang: str = "en",
        execution_id: str | None = None,
        fleet_url: str | None = None,
        line: str | None = None,
        recommendation_id: str | None = None,
        **_,
    ) -> dict:
        eid, snap, _fresh = pipeline.resolve_run(execution_id, fleet_url)
        kw: dict = {}
        if skill == "replan_and_dispatch_operations":
            kw["recommendation_id"] = recommendation_id
            kw["fleet_url"] = fleet_url
        resp = pipeline.run_stage(skill, snap, execution_id=eid, lang=lang, llm=_llm_fn(ctx), **kw)
        return _ok(resp)

    return handler


def _orchestrator_handler(ctx):
    def handler(lang: str = "en", fleet_url: str | None = None, **_) -> dict:
        eid, snap, _fresh = pipeline.resolve_run(None, fleet_url)
        resp = pipeline.run_pipeline(snap, execution_id=eid, lang=lang, llm=_llm_fn(ctx))
        return _ok(resp)

    return handler


def _ask_handler(ctx):
    def handler(question: str = "", fleet_url: str | None = None, **_) -> dict:
        q = str(question or "").strip()
        if not q:
            return {"success": False, "error": "Provide a question about a machine or the fleet."}
        st = simulate.handle_status({"url": fleet_url} if fleet_url else {})
        if not st.get("connected"):
            return {
                "success": False,
                "error": "Fleet simulator not reachable at {}. Start the IIOT fleet server "
                "(scripts/run_fleet_server.py, :5050) in the [Project]_IOTMock repo, then retry.".format(
                    st.get("source", "")
                ),
            }
        machines, scn = st.get("machines", []), st.get("scn")
        llm = _llm_fn(ctx)
        try:
            if llm is None:
                raise RuntimeError("no llm")
            system, user = analysis.build_ask_messages(q, machines, scn)
            out = analysis.normalize_ask(analysis.parse_json(llm(system, user)), machines, scn)
            src = os.environ.get("ATRIA_MODEL") or "gpt-5.4-mini"
        except Exception:  # noqa: BLE001 - degrade to deterministic
            out = analysis.deterministic_ask(q, machines, scn)
            src = "deterministic"
        text = out["answer"]
        if out.get("charts"):
            c = out["charts"][0]
            it = analysis.INTENT_BY_ID.get(c["intent"], {})
            text += "\n\nSuggested chart: {} ({}) for {}.".format(it.get("label"), it.get("chart"), c["machine"])
        return {"success": True, "output": "{}\n\n[live fleet - {} - source: {}]".format(text, st.get("plant", ""), src)}

    return handler


# ── tool parameter fragments ──────────────────────────────────────────────────
_LANG = {"type": "string", "enum": ["en", "vi"], "description": "Response language (default en). Set 'vi' when the user writes Vietnamese."}
_EXEC = {"type": "string", "description": "Execution id from a prior stage in THIS run -- pass it so every stage reads the same live snapshot (coherent numbers). Omit to start a fresh run; the id is returned in audit.execution_id."}
_FLEET = {"type": "string", "description": "Optional fleet API base URL (default http://127.0.0.1:5050)."}
_LINE = {"type": "string", "description": "Optional line/asset scope hint (e.g. 'M-02'). The console auto-selects the most at-risk line when omitted."}


def _stage_params(extra: dict | None = None) -> dict:
    props = {"lang": _LANG, "execution_id": _EXEC, "fleet_url": _FLEET, "line": _LINE}
    if extra:
        props.update(extra)
    return {"type": "object", "properties": props}


def register(ctx=None):
    """Return the Optimize pipeline's agent tools (empty if Minder's ToolSpec is unavailable)."""
    if ToolSpec is None:
        return []
    return [
        ToolSpec(
            name="measure_operational_performance",
            description=(
                "MEASURE (role: Production Performance Analyst). Answer 'what is happening / are we on "
                "target?' -- quantify actual-vs-expected for the most at-risk line on the live fleet "
                "simulator: attainment, production gap, OEE/availability/performance/quality, estimated "
                "lost units, with data-quality + confidence. Reads GET /api/fleet/snapshot. Assigns no "
                "causes. Returns audit.execution_id -- pass it to the next stage. Hand off to "
                "explain_performance_loss."
            ),
            parameters=_stage_params(),
            handler=_stage_handler(ctx, "measure_operational_performance"),
        ),
        ToolSpec(
            name="explain_performance_loss",
            description=(
                "EXPLAIN (role: Industrial/Reliability Engineer). Answer 'why did we miss target / what "
                "caused the loss?' -- break the measured gap into ranked loss drivers (material "
                "starvation, micro-stops, reduced speed, quality) with units/minutes, % explained, and "
                "the unexplained remainder. Inferred from the live fleet. Pass the execution_id from "
                "measure. Hand off to predict_operational_risk."
            ),
            parameters=_stage_params(),
            handler=_stage_handler(ctx, "explain_performance_loss"),
        ),
        ToolSpec(
            name="predict_operational_risk",
            description=(
                "PREDICT (role: Reliability/Production Forecaster). Answer 'what will happen next / will "
                "we meet target?' -- rule-based shift-end forecast, expected shortfall, attainment "
                "probability, and the intervention deadline (minutes remaining). Predicted, not a "
                "trained model -- uncertainty is stated. Pass the execution_id. Hand off to "
                "evaluate_operational_alternatives."
            ),
            parameters=_stage_params(),
            handler=_stage_handler(ctx, "predict_operational_risk"),
        ),
        ToolSpec(
            name="evaluate_operational_alternatives",
            description=(
                "EVALUATE (role: Operations Research Analyst). Answer 'what are our options?' -- compare "
                "the feasible recovery actions (expedite material, resequence, move operator, speed) on "
                "recovered units, cost, risk and score, list infeasible options with reasons (the +8% "
                "speed action is blocked when machine health < 0.70), and include a do-nothing baseline. "
                "Pass the execution_id. Hand off to recommend_operational_action."
            ),
            parameters=_stage_params(),
            handler=_stage_handler(ctx, "evaluate_operational_alternatives"),
        ),
        ToolSpec(
            name="recommend_operational_action",
            description=(
                "RECOMMEND (role: Operations/Shift Manager). Answer 'what should we do?' -- select the "
                "best action, state expected effect + residual risk + required approval role, and PREPARE "
                "a decision packet persisted with status 'awaiting_approval'. APPROVAL-REQUIRED mode: this "
                "NEVER actuates the machine. Pass the execution_id. A human approves (dashboard / "
                "optimize.py approve) before replan_and_dispatch_operations may execute."
            ),
            parameters=_stage_params(),
            handler=_stage_handler(ctx, "recommend_operational_action"),
        ),
        ToolSpec(
            name="replan_and_dispatch_operations",
            description=(
                "RE-PLAN & DISPATCH (role: Production Planner/Dispatch Coordinator). Apply an APPROVED "
                "decision -- dispatch the task and actuate the live simulator (POST maintenance/"
                "resolve-fault), then persist dispatch + outcome + audit. Refuses to actuate unless the "
                "decision status is 'approved' (returns awaiting_approval instead). Pass recommendation_id "
                "(and the execution_id). Closes the loop back to measure_operational_performance."
            ),
            parameters=_stage_params({"recommendation_id": {"type": "string", "description": "The recommendation id to dispatch (from recommend_operational_action / the decision store). Defaults to the current line's REC-LIVE id."}}),
            handler=_stage_handler(ctx, "replan_and_dispatch_operations"),
        ),
        ToolSpec(
            name="optimize_analyze_fleet",
            description=(
                "Run the WHOLE decision loop in one call -- Measure -> Explain -> Predict -> Evaluate -> "
                "Recommend over one live snapshot -- and return every stage's structured result (stops "
                "before actuation, which needs approval). Use for a quick end-to-end briefing; use the "
                "individual stage skills when the user asks a single operational question."
            ),
            parameters={"type": "object", "properties": {"lang": _LANG, "fleet_url": _FLEET}},
            handler=_orchestrator_handler(ctx),
        ),
        ToolSpec(
            name="optimize_ask",
            description=(
                "Ask the live fleet simulator a targeted question about a machine or the fleet (status, "
                "comparisons, why a machine is degrading) and get an answer plus a best-fit chart "
                "suggestion. Reads real telemetry from GET /api/fleet/snapshot."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Natural-language question about a machine or the fleet."},
                    "fleet_url": _FLEET,
                },
                "required": ["question"],
            },
            handler=_ask_handler(ctx),
        ),
    ]
