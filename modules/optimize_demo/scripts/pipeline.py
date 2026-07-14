"""pipeline.py -- the 6-stage operational decision pipeline for the Optimize module.

Measure -> Explain -> Predict -> Evaluate alternatives -> Recommend/Act -> Re-plan/Dispatch.

Each stage is a first-class skill: it takes a live-fleet SNAPSHOT (captured once and shared
across a chained run so the numbers stay coherent stage-to-stage), derives its structured fields
from the real numbers already in that snapshot (``simulate.build_scn`` / ``build_history``) and the
decision store, and returns the standard response object. **Code owns every number** -- KPIs,
losses, scores, AND the ``confidence`` / ``data_quality`` values; the LLM only writes the
human-readable ``summary`` prose (and can be absent, in which case a deterministic sentence is used).

Honest data sources: the only system of record is the IIOT fleet simulator (``/api/fleet/*``) plus
the decision store (``data/*.json``). The professional roles (MES/SCADA/APS/...) named in the tool
docs are analogies; ``sources[]`` lists the real endpoints actually queried.

This module may touch the network + disk (via ``simulate`` and ``store``); the LLM call itself is
*injected* by the caller (``tools.py`` -> ``ctx.llm_chat``; ``ai.py`` -> ``llm_chat``) so the pipeline
stays provider-agnostic.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Callable

try:  # sibling scripts on sys.path (conftest / tools.py / direct invocation all arrange this)
    from . import analysis, simulate, store
except ImportError:  # pragma: no cover - direct-invocation path
    import analysis  # type: ignore[no-redef]
    import simulate  # type: ignore[no-redef]
    import store  # type: ignore[no-redef]

LlmFn = Callable[[str, str], str]

# ── stage metadata (ordered) ──────────────────────────────────────────────────
# ``kind`` is the fact-label the stage's headline output carries (the spec's taxonomy:
# Observed / Calculated / Inferred / Predicted / Recommended / Executed).
STAGES: list[dict[str, Any]] = [
    {
        "skill": "measure_operational_performance",
        "role": "Production Performance Analyst",
        "kind": "Observed",
        "next": "explain_performance_loss",
    },
    {
        "skill": "explain_performance_loss",
        "role": "Industrial / Reliability Engineer",
        "kind": "Inferred",
        "next": "predict_operational_risk",
    },
    {
        "skill": "predict_operational_risk",
        "role": "Reliability / Production Forecaster",
        "kind": "Predicted",
        "next": "evaluate_operational_alternatives",
    },
    {
        "skill": "evaluate_operational_alternatives",
        "role": "Operations Research Analyst",
        "kind": "Calculated",
        "next": "recommend_operational_action",
    },
    {
        "skill": "recommend_operational_action",
        "role": "Operations / Shift Manager",
        "kind": "Recommended",
        "next": "replan_and_dispatch_operations",
    },
    {
        "skill": "replan_and_dispatch_operations",
        "role": "Production Planner / Dispatch Coordinator",
        "kind": "Executed",
        "next": "measure_operational_performance",
    },
]
STAGE_BY_SKILL = {s["skill"]: s for s in STAGES}
SKILLS = [s["skill"] for s in STAGES]

# Real endpoints/paths a stage may query (named honestly in ``sources[]``).
_SRC_FLEET = "IIOT fleet simulator: GET /api/fleet/snapshot + /api/fleet/summary"
_SRC_HISTORY = "telemetry history buffer: data/history.jsonl"
_SRC_DECISION = "decision store: data/decisions.json + audit.json"
_SRC_CONTROL = "IIOT fleet simulator control: POST /api/fleet/machines/<id>/maintenance|resolve-fault"


# ── small helpers ─────────────────────────────────────────────────────────────
def _pct(x: Any) -> int:
    try:
        return round(float(x) * 100)
    except (TypeError, ValueError):
        return 0


def _level(score: float) -> str:
    return "high" if score >= 0.8 else "medium" if score >= 0.6 else "low"


def _target_machine(snapshot: dict) -> dict:
    scn = snapshot.get("scn") or {}
    tid = str(scn.get("targetMachine") or "").upper()
    for m in snapshot.get("machines") or []:
        if str(m.get("id", "")).upper() == tid:
            return m
    return {}


def mint_execution_id(snapshot: dict) -> str:
    """Deterministic run id from snapshot content (no wall-clock / randomness)."""
    scn = snapshot.get("scn") or {}
    line = str(scn.get("line") or "LINE")
    seed = "{}|{}".format(line, snapshot.get("ts") or "")
    sig = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6].upper()
    return "OPT-{}-{}".format(line, sig)


def resolve_run(
    execution_id: str | None = None, fleet_url: str | None = None
) -> tuple[str, dict, bool]:
    """Return (execution_id, snapshot, fresh). Shared snapshot for coherence across a chained run.

    With an ``execution_id`` that resolves to a stored snapshot, reuse it (coherent numbers).
    Otherwise capture ONE live snapshot, persist it under a minted id, and return it.
    """
    if execution_id:
        snap = store.get_snapshot(execution_id)
        if snap:
            return execution_id, snap, False
    snap = simulate.handle_status({"url": fleet_url} if fleet_url else {})
    eid = execution_id or mint_execution_id(snap)
    try:
        store.save_snapshot(eid, snap)
    except OSError:  # best-effort persistence; a chained run still works within one process
        pass
    return eid, snap, True


# ── data-quality + confidence (DERIVED from real signals, never model-produced) ──
_FULL_FIELDS = ("oee", "avail", "perf", "qual", "health", "temp", "vib", "thru", "target")


def _latency_seconds(ts: str | None) -> int | None:
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(ts)
        now = datetime.now(t.tzinfo) if t.tzinfo else datetime.now()
        return max(0, int((now - t).total_seconds()))
    except (ValueError, TypeError):
        return None


def data_quality_from(snapshot: dict) -> dict:
    machines = snapshot.get("machines") or []
    total = len(machines)
    complete = sum(1 for m in machines if all(m.get(k) is not None for k in _FULL_FIELDS))
    completeness = round(complete / total, 3) if total else 0.0
    warnings: list[str] = []
    if not snapshot.get("connected"):
        warnings.append("fleet simulator not connected -- figures are unavailable/stale")
    if not total:
        warnings.append("no machines in snapshot")
    if total and complete < total:
        warnings.append("{} machine(s) missing telemetry fields".format(total - complete))
    return {
        "completeness": completeness,
        "latest_timestamp": snapshot.get("ts"),
        "latency_seconds": _latency_seconds(snapshot.get("ts")),
        "warnings": warnings,
    }


def _constraints_ok(scn: dict) -> bool:
    return all(c.get("r") == "passed" for c in (scn.get("constraints") or []))


def confidence_for(skill: str, snapshot: dict) -> dict:
    dq = data_quality_from(snapshot)
    connected = bool(snapshot.get("connected"))
    base = dq["completeness"] if connected else 0.2
    scn = snapshot.get("scn") or {}
    alts = scn.get("alternatives") or []
    rec = alts[0] if alts else {}
    if skill == "measure_operational_performance":
        score = round(0.60 + 0.35 * base, 2)
        expl = "Directly observed telemetry from the live fleet; scaled by data completeness."
    elif skill == "explain_performance_loss":
        score = round(0.55 + 0.30 * base, 2)
        expl = "Loss attribution is a modeled proportional split of the measured gap (inferred)."
    elif skill == "predict_operational_risk":
        score = round(0.45 + 0.25 * base, 2)
        expl = "Rule-based projection from the current rate over the remaining shift, not a trained model."
    elif skill == "evaluate_operational_alternatives":
        feas = [float(a.get("confidence") or 0) for a in alts if a.get("feasible")]
        score = round(sum(feas) / len(feas), 2) if feas else 0.4
        expl = "Mean confidence of the feasible alternatives in the scored catalog."
    elif skill == "recommend_operational_action":
        score = round(float(rec.get("confidence") or 0.5) * (1.0 if _constraints_ok(scn) else 0.7), 2)
        expl = "Confidence of the top-ranked feasible action; reduced if a hard constraint failed."
    elif skill == "replan_and_dispatch_operations":
        score = 0.9 if connected else 0.3
        expl = "Reflects whether the dispatch/actuation reached the live simulator."
    else:
        score, expl = 0.5, ""
    return {"level": _level(score), "score": score, "explanation": expl}


# ── standard response envelope (the spec's exact shape) ───────────────────────
def _scope(snapshot: dict) -> dict:
    scn = snapshot.get("scn") or {}
    return {
        "plant": snapshot.get("plant"),
        "line": scn.get("line"),
        "asset": scn.get("targetMachine"),
        "shift": scn.get("shift"),
        "time_end": snapshot.get("ts"),
    }


def _audit(skill: str, snapshot: dict, execution_id: str | None, tools_used, model_version) -> dict:
    scn = snapshot.get("scn") or {}
    return {
        "execution_id": execution_id,
        "skill": skill,
        "tools_used": tools_used or [],
        "ruleset_version": (scn.get("versions") or {}).get("ruleset"),
        "model_version": model_version,
        "evidence": scn.get("evidence") or [],
    }


def standard_response(
    skill: str,
    snapshot: dict,
    summary: str,
    *,
    execution_id: str | None = None,
    status: str = "completed",
    observations=None,
    calculations=None,
    findings=None,
    assumptions=None,
    constraints=None,
    next_skill: str | None = None,
    sources=None,
    tools_used=None,
    model_version: str | None = None,
    source: str = "fallback",
) -> dict:
    return {
        "ok": True,
        "skill": skill,
        "status": status,
        "scope": _scope(snapshot),
        "summary": summary,
        "observations": observations or [],
        "calculations": calculations or [],
        "findings": findings or [],
        "assumptions": assumptions or [],
        "constraints": constraints or [],
        "recommended_next_skill": next_skill,
        "data_quality": data_quality_from(snapshot),
        "confidence": confidence_for(skill, snapshot),
        "sources": sources or [_SRC_FLEET],
        "source": source,  # prose provenance: model id when the LLM wrote it, else "fallback"
        "audit": _audit(skill, snapshot, execution_id, tools_used, model_version),
    }


# ── prose: deterministic (EN + VI) first, LLM override if a callable is provided ──
def _figs(snapshot: dict) -> dict:
    scn = snapshot.get("scn") or {}
    alts = scn.get("alternatives") or []
    losses = scn.get("losses") or []
    gap = int(scn.get("gap") or 0)
    return {
        "scn": scn,
        "tm": _target_machine(snapshot),
        "line": scn.get("line"),
        "attain_pct": _pct(scn.get("attainBefore")),
        "gap": gap,
        "shortfall": max(1, -gap),
        "losses": losses,
        "top_loss": losses[0] if losses else {},
        "alts": alts,
        "rec": alts[0] if alts else {},
        "feasible": [a for a in alts if a.get("feasible")],
    }


def _det_prose(skill: str, snapshot: dict, lang: str) -> str:
    """Rule-based one/two-sentence narrative per stage, grounded in scn. EN + VI."""
    f = _figs(snapshot)
    scn, tm, rec = f["scn"], f["tm"], f["rec"]
    line = f["line"] or "the line"
    vi = lang == "vi"
    if skill == "measure_operational_performance":
        if vi:
            return (
                "Chuyền {ln} ({tm}) đã sản xuất {cur}/{tgt} sản phẩm; dự báo {fc} -- "
                "thiếu {gap} ({at}% đạt mục tiêu), OEE {oee}%.".format(
                    ln=line, tm=scn.get("targetMachine"), cur=scn.get("current"),
                    tgt=scn.get("target"), fc=scn.get("forecastBase"), gap=abs(f["gap"]),
                    at=f["attain_pct"], oee=_pct(tm.get("oee")))
            )
        return (
            "Line {ln} ({tm}) has produced {cur} of {tgt} units; forecast {fc} leaves a gap of "
            "{gap} ({at}% attainment), OEE {oee}%.".format(
                ln=line, tm=scn.get("targetMachine"), cur=scn.get("current"),
                tgt=scn.get("target"), fc=scn.get("forecastBase"), gap=f["gap"],
                at=f["attain_pct"], oee=_pct(tm.get("oee")))
        )
    if skill == "explain_performance_loss":
        top = f["top_loss"]
        if vi:
            return (
                "Tổn thất lớn nhất là {ty} (~{u} sản phẩm); micro-stop và giảm tốc độ theo sau, "
                "cùng nhau giải thích phần lớn khoảng thiếu hụt {sf} sản phẩm.".format(
                    ty=top.get("type", "material starvation"), u=top.get("units", 0), sf=f["shortfall"])
            )
        return (
            "The largest loss is {ty} (~{u} units); micro-stops and reduced speed follow, "
            "together accounting for most of the {sf}-unit shortfall.".format(
                ty=top.get("type", "material starvation"), u=top.get("units", 0), sf=f["shortfall"])
        )
    if skill == "predict_operational_risk":
        if vi:
            return (
                "Nếu không can thiệp, ca kíp kết thúc gần {fc} sản phẩm -- thiếu {gap} so với mục "
                "tiêu; còn {mr} phút để hành động.".format(
                    fc=scn.get("forecastBase"), gap=abs(f["gap"]), mr=scn.get("minutesRemaining"))
            )
        return (
            "Without action the shift finishes near {fc} units -- {gap} short of target; "
            "roughly {mr} minutes remain to intervene.".format(
                fc=scn.get("forecastBase"), gap=abs(f["gap"]), mr=scn.get("minutesRemaining"))
        )
    if skill == "evaluate_operational_alternatives":
        if vi:
            return (
                "{n} phương án khả thi đã được chấm điểm; phương án tăng tốc +8% bị chặn khi sức "
                "khỏe máy dưới ngưỡng 0.70.".format(n=len(f["feasible"]))
            )
        return (
            "{n} feasible recovery actions were scored; the +8% speed option is blocked when "
            "machine health is below the 0.70 operating limit.".format(n=len(f["feasible"]))
        )
    if skill == "recommend_operational_action":
        appr = rec.get("approval")
        if vi:
            s = "Đề xuất: {ty} (+{r} sản phẩm, rủi ro {rk}).".format(
                ty=rec.get("type", "prioritize material"), r=rec.get("recovered", 0),
                rk=rec.get("risk", "low"))
            return s + (" Cần {a} phê duyệt trước khi thực thi.".format(a=appr) if appr else " Chờ phê duyệt.")
        s = "Recommended: {ty} (+{r} units, {rk} risk).".format(
            ty=rec.get("type", "prioritize material"), r=rec.get("recovered", 0), rk=rec.get("risk", "low"))
        return s + (" {a} approval required before execution.".format(a=appr) if appr else " Awaiting approval.")
    if skill == "replan_and_dispatch_operations":
        if vi:
            return "Chờ quyết định được phê duyệt trước khi điều phối và tác động lên máy."
        return "Awaiting an approved decision before dispatching and actuating the machine."
    return ""


def _stage_prompt(skill: str, structured: dict, snapshot: dict, lang: str) -> tuple[str, str]:
    """A focused per-stage prompt: the model writes ONLY this stage's prose from the given numbers."""
    meta = STAGE_BY_SKILL.get(skill, {})
    purpose = {
        "measure_operational_performance": "state what is happening and quantify actual-vs-expected",
        "explain_performance_loss": "explain why the gap exists, citing the ranked loss drivers",
        "predict_operational_risk": "state what is likely to happen next and by when",
        "evaluate_operational_alternatives": "compare the feasible recovery options and their trade-offs",
        "recommend_operational_action": "recommend the single best action and its expected effect",
        "replan_and_dispatch_operations": "summarize the dispatch/execution outcome",
    }.get(skill, "summarize this stage")
    lang_line = "Write in Vietnamese (Tieng Viet)." if lang == "vi" else "Write in English."
    system = (
        "You are Minder, the {role} in a manufacturing Optimize console. In 1-3 sentences, {purpose}, "
        "using ONLY the numbers in DATA (never invent figures). {lang} Reply with plain prose only -- "
        "no JSON, no markdown tables.".format(role=meta.get("role", "analyst"), purpose=purpose, lang=lang_line)
    )
    import json as _json

    user = "DATA:\n" + _json.dumps(structured, ensure_ascii=False)
    return system, user


def _prose(skill: str, structured: dict, snapshot: dict, lang: str, llm: LlmFn | None) -> tuple[str, str]:
    det = _det_prose(skill, snapshot, lang)
    if llm is None:
        return det, "fallback"
    try:
        system, user = _stage_prompt(skill, structured, snapshot, lang)
        txt = (llm(system, user) or "").strip()
        if txt:
            return txt, "llm"
    except Exception:  # noqa: BLE001 - always degrade to deterministic prose
        pass
    return det, "fallback"


# ── the six stages ────────────────────────────────────────────────────────────
def _offline(skill: str, snapshot: dict, execution_id: str | None, lang: str) -> dict:
    msg = (
        "Bộ mô phỏng fleet chưa kết nối; không thể chạy giai đoạn này trên dữ liệu trực tiếp."
        if lang == "vi"
        else "The fleet simulator is not connected, so this stage cannot run on live data."
    )
    return standard_response(
        skill, snapshot, msg, execution_id=execution_id, status="degraded",
        next_skill=STAGE_BY_SKILL[skill]["next"], sources=[_SRC_FLEET],
    )


def _ready(snapshot: dict) -> bool:
    return bool(snapshot.get("connected")) and bool(snapshot.get("scn"))


def stage_measure(snapshot, execution_id=None, lang="en", llm=None, **_):
    skill = "measure_operational_performance"
    if not _ready(snapshot):
        return _offline(skill, snapshot, execution_id, lang)
    f = _figs(snapshot)
    scn, tm = f["scn"], f["tm"]
    observations = [
        {"label": "line", "value": f["line"], "kind": "Observed"},
        {"label": "target_machine", "value": scn.get("targetMachine"), "kind": "Observed"},
        {"label": "machine_state", "value": tm.get("state"), "kind": "Observed"},
        {"label": "planned_units", "value": scn.get("target"), "kind": "Observed"},
        {"label": "actual_units", "value": scn.get("current"), "kind": "Observed"},
    ]
    calculations = [
        {"metric": "attainment_pct", "value": f["attain_pct"], "kind": "Calculated"},
        {"metric": "production_gap_units", "value": f["gap"], "kind": "Calculated"},
        {"metric": "estimated_lost_units", "value": f["shortfall"], "kind": "Calculated"},
        {"metric": "oee_pct", "value": _pct(tm.get("oee")), "kind": "Calculated"},
        {"metric": "availability_pct", "value": _pct(tm.get("avail")), "kind": "Calculated"},
        {"metric": "performance_pct", "value": _pct(tm.get("perf")), "kind": "Calculated"},
        {"metric": "quality_pct", "value": _pct(tm.get("qual")), "kind": "Calculated"},
        {"metric": "downtime_minutes", "value": tm.get("downMin"), "kind": "Calculated"},
    ]
    summary, src = _prose(skill, {"observations": observations, "calculations": calculations}, snapshot, lang, llm)
    return standard_response(
        skill, snapshot, summary, execution_id=execution_id,
        observations=observations, calculations=calculations,
        next_skill="explain_performance_loss", sources=[_SRC_FLEET],
        tools_used=["simulate.handle_status"], model_version=(src if src == "llm" else None), source=src,
    )


def stage_explain(snapshot, execution_id=None, lang="en", llm=None, **_):
    skill = "explain_performance_loss"
    if not _ready(snapshot):
        return _offline(skill, snapshot, execution_id, lang)
    f = _figs(snapshot)
    losses = f["losses"]
    explained = sum(int(x.get("units") or 0) for x in losses)
    findings = [
        {
            "cause": x.get("type"),
            "lost_units": x.get("units"),
            "minutes": x.get("min"),
            "confidence": "probable",
            "kind": "Inferred",
        }
        for x in losses
    ]
    calculations = [
        {"metric": "gap_units", "value": f["shortfall"], "kind": "Calculated"},
        {"metric": "explained_units", "value": explained, "kind": "Calculated"},
        {
            "metric": "explained_pct",
            "value": round(explained / f["shortfall"] * 100) if f["shortfall"] else 0,
            "kind": "Calculated",
        },
        {"metric": "unexplained_units", "value": max(0, f["shortfall"] - explained), "kind": "Calculated"},
    ]
    summary, src = _prose(skill, {"findings": findings, "calculations": calculations}, snapshot, lang, llm)
    return standard_response(
        skill, snapshot, summary, execution_id=execution_id,
        findings=findings, calculations=calculations,
        assumptions=["Loss split is a proportional attribution of the measured gap, not per-event traced."],
        next_skill="predict_operational_risk", sources=[_SRC_FLEET],
        tools_used=["simulate.handle_status"], model_version=(src if src == "llm" else None), source=src,
    )


def stage_predict(snapshot, execution_id=None, lang="en", llm=None, **_):
    skill = "predict_operational_risk"
    if not _ready(snapshot):
        return _offline(skill, snapshot, execution_id, lang)
    f = _figs(snapshot)
    scn = f["scn"]
    findings = [
        {
            "event": "shift_end_forecast",
            "expected_units": scn.get("forecastBase"),
            "shortfall_units": abs(f["gap"]),
            "attainment_probability_pct": f["attain_pct"],
            "kind": "Predicted",
        }
    ]
    calculations = [
        {"metric": "forecast_units", "value": scn.get("forecastBase"), "kind": "Predicted"},
        {"metric": "minutes_remaining", "value": scn.get("minutesRemaining"), "kind": "Calculated"},
        {"metric": "intervention_deadline_minutes", "value": scn.get("minutesRemaining"), "kind": "Calculated"},
    ]
    summary, src = _prose(skill, {"findings": findings, "calculations": calculations}, snapshot, lang, llm)
    return standard_response(
        skill, snapshot, summary, execution_id=execution_id,
        findings=findings, calculations=calculations,
        assumptions=[
            "Forecast is a rule-based projection from the current rate over the remaining shift; "
            "not a trained model.",
            "Model refs: {}".format(scn.get("versions") or {}),
        ],
        next_skill="evaluate_operational_alternatives", sources=[_SRC_FLEET, _SRC_HISTORY],
        tools_used=["simulate.handle_status", "simulate.build_history"],
        model_version=(src if src == "llm" else None), source=src,
    )


def stage_evaluate(snapshot, execution_id=None, lang="en", llm=None, **_):
    skill = "evaluate_operational_alternatives"
    if not _ready(snapshot):
        return _offline(skill, snapshot, execution_id, lang)
    f = _figs(snapshot)
    scn = f["scn"]
    findings = [
        {
            "action_id": a.get("id"),
            "type": a.get("type"),
            "feasible": a.get("feasible"),
            "expected_recovered_units": a.get("recovered"),
            "cost": a.get("cost"),
            "risk": a.get("risk"),
            "score": a.get("score"),
            "attainment_after": a.get("attainAfter"),
            "rejection_reason": a.get("rejection"),
            "kind": "Calculated",
        }
        for a in f["alts"]
    ]
    constraints = [{"constraint": c.get("c"), "result": c.get("r")} for c in (scn.get("constraints") or [])]
    summary, src = _prose(skill, {"alternatives": findings, "constraints": constraints}, snapshot, lang, llm)
    return standard_response(
        skill, snapshot, summary, execution_id=execution_id,
        findings=findings, constraints=constraints,
        assumptions=["A do-nothing baseline (ACT-000) is included for comparison."],
        next_skill="recommend_operational_action", sources=[_SRC_FLEET],
        tools_used=["simulate.handle_status"], model_version=(src if src == "llm" else None), source=src,
    )


# Short stage labels for the persisted reasoning trace (Approved History transcript).
_STAGE_LABEL = {
    "measure_operational_performance": "Measure",
    "explain_performance_loss": "Explain",
    "predict_operational_risk": "Predict",
    "evaluate_operational_alternatives": "Evaluate",
    "recommend_operational_action": "Recommend",
}


def _consideration_log(snapshot: dict, lang: str) -> list[dict]:
    """The captured per-stage reasoning trace (Measure..Recommend) persisted with the decision.

    Deterministic one-liners grounded in THIS snapshot's numbers, so Approved History replays the
    real reasoning that produced the decision rather than reconstructing it from fields at read time.
    (The 'Act' line is rendered by the dashboard from the decision's lifecycle/outcome.)
    """
    return [
        {"stage": _STAGE_LABEL[skill], "text": _det_prose(skill, snapshot, lang)}
        for skill in _STAGE_LABEL
    ]


def _decision_packet(snapshot: dict, rec: dict, status: str, lang: str = "en") -> dict:
    """Build the persisted decision object (mirrors the dashboard's recDecisionObj schema)."""
    scn = snapshot.get("scn") or {}
    alts = scn.get("alternatives") or []
    return {
        "schema_version": "1.0",
        "recommendation_id": scn.get("recId"),
        "recommendation_version": 1,
        "status": status,
        "scope": {
            "plant": snapshot.get("plant"),
            "line": scn.get("line"),
            "work_order": scn.get("wo"),
            "shift": scn.get("shift"),
        },
        "current_state": {
            "current_good_output": scn.get("current"),
            "target_output": scn.get("target"),
            "forecast_output": scn.get("forecastBase"),
            "forecast_gap": scn.get("gap"),
            "target_attainment_probability": scn.get("attainBefore"),
        },
        "recommended_action": {
            "action_id": rec.get("id"),
            "type": rec.get("type"),
            "parameters": {"detail": rec.get("detail")},
        },
        "expected_effect": {
            "forecast_output_after_action": rec.get("forecastAfter"),
            "recovered_units": rec.get("recovered"),
            "target_attainment_probability_after": rec.get("attainAfter"),
        },
        "alternatives": [
            {
                "action_id": a.get("id"),
                "type": a.get("type"),
                "score": a.get("score"),
                "feasibility": "feasible" if a.get("feasible") else "infeasible",
                "expected_recovered_units": a.get("recovered"),
                "risk_level": a.get("risk"),
                "rejection_reason": a.get("rejection"),
            }
            for a in alts
        ],
        "confidence": {"overall": rec.get("confidence")},
        "risk": {"level": rec.get("risk")},
        "constraints": {
            "result": "passed" if _constraints_ok(scn) else "failed",
            "checks": [{"constraint": c.get("c"), "result": c.get("r")} for c in (scn.get("constraints") or [])],
        },
        "evidence": {"event_ids": scn.get("evidence") or []},
        "approval": {"required": bool(rec.get("approval")), "required_role": rec.get("approval")},
        "versions": scn.get("versions") or {},
        "consideration_log": _consideration_log(snapshot, lang),
    }


def stage_recommend(snapshot, execution_id=None, lang="en", llm=None, at=None, **_):
    """Recommend the best action and PREPARE a decision packet (status awaiting_approval).

    Approval-required mode: this stage never actuates. It persists a decision awaiting approval;
    a human approves (dashboard / optimize.py approve) before ``replan`` may actuate.
    """
    skill = "recommend_operational_action"
    if not _ready(snapshot):
        return _offline(skill, snapshot, execution_id, lang)
    f = _figs(snapshot)
    rec = f["rec"]
    packet = _decision_packet(snapshot, rec, status="awaiting_approval", lang=lang)
    persisted = None
    try:
        persisted = store.save_decision(packet, at=at)
    except (OSError, ValueError):  # persistence is best-effort; the recommendation still stands
        pass
    findings = [
        {
            "recommended_action": rec.get("type"),
            "action_id": rec.get("id"),
            "expected_recovered_units": rec.get("recovered"),
            "forecast_after": rec.get("forecastAfter"),
            "attainment_after": rec.get("attainAfter"),
            "risk": rec.get("risk"),
            "cost": rec.get("cost"),
            "kind": "Recommended",
        }
    ]
    approval_role = rec.get("approval")
    constraints = [
        {"constraint": "execution_mode", "result": "approval-required"},
        {"constraint": "approval_role", "result": approval_role or "shift_supervisor"},
        {"constraint": "actuated", "result": "no -- awaiting approval"},
    ]
    summary, src = _prose(skill, {"recommended": findings[0], "approval_role": approval_role}, snapshot, lang, llm)
    resp = standard_response(
        skill, snapshot, summary, execution_id=execution_id, status="awaiting_approval",
        findings=findings, constraints=constraints,
        next_skill="replan_and_dispatch_operations", sources=[_SRC_FLEET, _SRC_DECISION],
        tools_used=["simulate.handle_status", "store.save_decision"],
        model_version=(src if src == "llm" else None), source=src,
    )
    resp["decision"] = persisted or packet
    resp["recommendation_id"] = packet.get("recommendation_id")
    resp["execution_mode"] = "approval-required"
    return resp


def stage_replan(snapshot, execution_id=None, lang="en", llm=None, recommendation_id=None, fleet_url=None, at=None, **_):
    """Dispatch + actuate -- ONLY after the decision is approved (approval-required mode)."""
    skill = "replan_and_dispatch_operations"
    if not _ready(snapshot):
        return _offline(skill, snapshot, execution_id, lang)
    scn = snapshot.get("scn") or {}
    rec_id = recommendation_id or scn.get("recId")
    decision = store.get_decision(str(rec_id)) if rec_id else None
    dstatus = (decision or {}).get("status")

    if decision is None or dstatus not in ("approved", "dispatched", "completed"):
        msg = (
            "Chưa có quyết định được phê duyệt cho {rid}; không tác động lên máy.".format(rid=rec_id)
            if lang == "vi"
            else "No approved decision for {rid} -- not actuating. A human must approve first.".format(rid=rec_id)
        )
        resp = standard_response(
            skill, snapshot, msg, execution_id=execution_id, status="awaiting_approval",
            constraints=[
                {"constraint": "decision_status", "result": dstatus or "missing"},
                {"constraint": "actuated", "result": "no -- approval required"},
            ],
            next_skill="measure_operational_performance", sources=[_SRC_DECISION],
            tools_used=["store.get_decision"], source="fallback",
        )
        resp["recommendation_id"] = rec_id
        return resp

    # Approved -> actuate the live simulator + persist dispatch/outcome.
    action = (decision.get("recommended_action") or {}).get("type") or ""
    act_kind = "speed" if "speed" in action.lower() else "service"
    machine = scn.get("targetMachine")
    actu = simulate.handle_actuate({"machine": machine, "action": act_kind, "url": fleet_url})
    recovered = ((decision.get("expected_effect") or {}).get("recovered_units")) or 0
    try:
        store.dispatch(str(rec_id), "move", command={"machine": machine, "action": act_kind}, at=at)
        store.set_status(
            str(rec_id), "completed", event_type="outcome_recorded", at=at,
            extra={"recovered_units": recovered, "actuated": bool(actu.get("actuated"))},
        )
    except (OSError, ValueError):
        pass
    findings = [
        {
            "dispatched_to": "move",
            "machine": machine,
            "action": act_kind,
            "endpoint": actu.get("endpoint"),
            "actuated": actu.get("actuated"),
            "expected_recovered_units": recovered,
            "kind": "Executed",
        }
    ]
    summary, src = _prose(skill, {"dispatch": findings[0]}, snapshot, lang, llm)
    resp = standard_response(
        skill, snapshot, summary, execution_id=execution_id,
        status="completed" if actu.get("actuated") else "failed",
        findings=findings,
        constraints=[
            {"constraint": "decision_status", "result": dstatus},
            {"constraint": "actuated", "result": "yes" if actu.get("actuated") else "no"},
        ],
        next_skill="measure_operational_performance", sources=[_SRC_CONTROL, _SRC_DECISION],
        tools_used=["simulate.handle_actuate", "store.dispatch", "store.set_status"],
        model_version=(src if src == "llm" else None), source=src,
    )
    resp["recommendation_id"] = rec_id
    resp["actuation"] = actu
    return resp


_STAGE_FN: dict[str, Callable[..., dict]] = {
    "measure_operational_performance": stage_measure,
    "explain_performance_loss": stage_explain,
    "predict_operational_risk": stage_predict,
    "evaluate_operational_alternatives": stage_evaluate,
    "recommend_operational_action": stage_recommend,
    "replan_and_dispatch_operations": stage_replan,
}


def run_stage(skill: str, snapshot: dict, execution_id=None, lang="en", llm=None, **kw) -> dict:
    fn = _STAGE_FN.get(skill)
    if fn is None:
        return {"ok": False, "error": "unknown stage: {!r}".format(skill)}
    return fn(snapshot, execution_id=execution_id, lang=lang, llm=llm, **kw)


def run_pipeline(snapshot: dict, execution_id=None, lang="en", llm=None, at=None) -> dict:
    """Run Measure -> ... -> Recommend over ONE snapshot (stops before actuation; that needs approval).

    Returns the per-stage standard responses PLUS flat prose keys for the legacy dashboard consumer.
    """
    order = [
        "measure_operational_performance",
        "explain_performance_loss",
        "predict_operational_risk",
        "evaluate_operational_alternatives",
        "recommend_operational_action",
    ]
    stages = {}
    flat_key = {
        "measure_operational_performance": "measure",
        "explain_performance_loss": "explain",
        "predict_operational_risk": "predict",
        "evaluate_operational_alternatives": "evaluate",
        "recommend_operational_action": "recommend",
    }
    out: dict[str, Any] = {"ok": True, "execution_id": execution_id, "stages": stages}
    src = "fallback"
    for skill in order:
        resp = run_stage(skill, snapshot, execution_id=execution_id, lang=lang, llm=llm, at=at)
        stages[skill] = resp
        out[flat_key[skill]] = resp.get("summary", "")
        if resp.get("source") and resp["source"] != "fallback":
            src = resp["source"]
    out["source"] = src
    out["recommendation_id"] = (stages.get("recommend_operational_action") or {}).get("recommendation_id")
    return out
