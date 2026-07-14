"""Shared, LLM-agnostic analysis core for the Optimize console.

Used by both the bridge-invoked ``ai.py`` (dashboard Ask AI + the decision narrative) and the
atria skill ``tools.py``. There is **no network and no LLM here** — only context building, the
9-intent chart picker, deterministic fallbacks, and robust JSON parsing. The authoritative
numbers always come from the caller (live sim / ``simulate.build_scn``); this module never
invents metrics — it only selects the machine + chart intent and phrases text around real values.
"""

from __future__ import annotations

import json
import re
from typing import Any

# The 9 analytic intents (mirrors the dashboard's INTENTS + the user's chart guide). Each maps to
# exactly one chart the dashboard already knows how to draw from live data.
INTENTS: list[dict[str, str]] = [
    {
        "id": "throughput",
        "label": "Live throughput",
        "chart": "Time-series line + band",
        "why": "Best for one metric over time; the target band shows deviation instantly.",
    },
    {
        "id": "cycle",
        "label": "Cycle-time stability",
        "chart": "Histogram",
        "why": "Shows the spread and outliers that a line chart hides.",
    },
    {
        "id": "downtime",
        "label": "Downtime causes",
        "chart": "Pareto",
        "why": "Ranks causes and overlays the cumulative 80/20 curve so you fix the biggest first.",
    },
    {
        "id": "vibtemp",
        "label": "Vibration & temp",
        "chart": "Dual-line + warning band",
        "why": "Surfaces how close the machine is running to its thermal and vibration limits.",
    },
    {
        "id": "state",
        "label": "Run / idle / down",
        "chart": "State timeline (Gantt)",
        "why": "Reveals utilization and stoppage patterns across the whole shift.",
    },
    {
        "id": "oee",
        "label": "OEE breakdown",
        "chart": "Waterfall",
        "why": "Decomposes 100% into availability, performance and quality losses down to OEE.",
    },
    {
        "id": "anomaly",
        "label": "Anomaly detection",
        "chart": "SPC control chart",
        "why": "Separates real anomalies from normal process variation using control limits.",
    },
    {
        "id": "peer",
        "label": "Peer comparison",
        "chart": "Ranked bars vs fleet",
        "why": "Shows this machine's relative standing on a KPI, highlighted against all peers.",
    },
    {
        "id": "corr",
        "label": "Temp vs defects",
        "chart": "Scatter",
        "why": "Reveals whether two variables move together — a correlation a trend hides.",
    },
]
INTENT_IDS = {it["id"] for it in INTENTS}
INTENT_BY_ID = {it["id"]: it for it in INTENTS}

# Keyword → intent, checked in order (first match wins) for free-text questions.
_KW: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"vibrat|temperat|overheat|\bhot\b|therm"), "vibtemp"),
    (re.compile(r"down|stopp|fault|breakdown|outage"), "downtime"),
    (re.compile(r"cycle|takt|speed of a? ?cycle"), "cycle"),
    (re.compile(r"anomal|spike|out of control|unusual|spc"), "anomaly"),
    (re.compile(r"oee|breakdown of|avail.*perf|losses"), "oee"),
    (re.compile(r"compar|peer|rank|versus|vs\b|best|worst"), "peer"),
    (re.compile(r"defect|quality|scrap|reject|correlat"), "corr"),
    (re.compile(r"state|idle|utilis|utiliz|gantt|timeline"), "state"),
    (re.compile(r"throughput|output|units|rate|produc"), "throughput"),
]


def _pct(x: Any) -> int:
    try:
        return round(float(x) * 100)
    except (TypeError, ValueError):
        return 0


def pick_intent(m: dict) -> str:
    """Deterministic best-fit chart for a machine (mirrors the dashboard's pickIntent)."""
    if not m:
        return "throughput"
    if m.get("state") == "down":
        return "downtime"
    if m.get("atRisk"):
        return "vibtemp"
    if float(m.get("perf") or 1.0) < 0.86:
        return "oee"
    if m.get("state") == "changeover":
        return "state"
    return "throughput"


def intent_from_question(q: str, m: dict | None) -> str:
    ql = (q or "").lower()
    for rx, iid in _KW:
        if rx.search(ql):
            return iid
    return pick_intent(m) if m else "throughput"


def find_machine(q: str, machines: list) -> dict | None:
    """Extract an M-NN reference from the question and return that machine, if present."""
    mm = re.search(r"m[- ]?0?(\d{1,2})", (q or "").lower())
    if mm:
        mid = "M-%02d" % int(mm.group(1))
        for x in machines:
            if str(x.get("id", "")).upper() == mid:
                return x
    return None


def machine_row(m: dict) -> dict:
    """One machine as a compact table row (percent-formatted, real values)."""
    return {
        "id": m.get("id"),
        "cell": m.get("cell"),
        "type": m.get("type"),
        "state": m.get("state"),
        "oee": _pct(m.get("oee")),
        "avail": _pct(m.get("avail")),
        "perf": _pct(m.get("perf")),
        "qual": _pct(m.get("qual")),
        "health": _pct(m.get("health")),
        "temp": round(float(m.get("temp") or 0), 1),
        "vib": round(float(m.get("vib") or 0), 2),
        "thru": int(m.get("thru") or 0),
        "target": int(m.get("target") or 0),
        "defect": round(float(m.get("defect") or 0), 2),
        "downMin": int(m.get("downMin") or 0),
        "atRisk": bool(m.get("atRisk")),
    }


def fleet_context(machines: list, scn: dict | None) -> str:
    """A compact, token-frugal description of the live fleet for the LLM prompt."""
    lines = [
        "id | cell | type | state | oee% | avail% | perf% | qual% | health% | temp | vib | "
        "thru/target | defect% | downMin | atRisk"
    ]
    for m in machines:
        r = machine_row(m)
        lines.append(
            f"{r['id']} | {r['cell']} | {r['type']} | {r['state']} | {r['oee']} | {r['avail']} | "
            f"{r['perf']} | {r['qual']} | {r['health']} | {r['temp']} | {r['vib']} | "
            f"{r['thru']}/{r['target']} | {r['defect']} | {r['downMin']} | {r['atRisk']}"
        )
    ctx = "LIVE FLEET (each row is one machine, real current telemetry):\n" + "\n".join(lines)
    if scn:
        ctx += (
            f"\n\nLIVE RECOMMENDATION CONTEXT: line {scn.get('line')} target {scn.get('target')} "
            f"current {scn.get('current')} forecast {scn.get('forecastBase')} gap {scn.get('gap')} "
            f"attainment {scn.get('attainBefore')} targetMachine {scn.get('targetMachine')}"
        )
    return ctx


def _worst(machines: list) -> dict | None:
    if not machines:
        return None
    down = [m for m in machines if m.get("state") == "down"]
    pool = down or [m for m in machines if m.get("atRisk")] or machines
    return sorted(pool, key=lambda m: float(m.get("oee") or 1.0))[0]


# ── deterministic fallbacks (no LLM) ──────────────────────────────────────────


def deterministic_ask(question: str, machines: list, scn: dict | None) -> dict:
    """Rule-based Ask-AI answer used when the LLM key is missing or a call fails."""
    m = find_machine(question, machines) or _worst(machines)
    if not m:
        return {
            "answer": "No fleet data is available yet.",
            "table": None,
            "charts": [],
            "follow_ups": [it["label"] for it in INTENTS[:3]],
            "mode": "fallback",
        }
    intent = intent_from_question(question, m)
    r = machine_row(m)
    bits = [
        f"{r['id']} ({r['type']}, {r['cell']} cell) is **{r['state']}** with OEE {r['oee']}% "
        f"and health {r['health']}%."
    ]
    if r["state"] == "down":
        bits.append(f"It has lost {r['downMin']} min this shift.")
    if r["atRisk"]:
        bits.append("It is flagged at-risk (low health + high runtime).")
    if r["temp"] or r["vib"]:
        bits.append(f"Temperature {r['temp']}°C, vibration {r['vib']} mm/s.")
    it = INTENT_BY_ID[intent]
    bits.append(f"Best chart: {it['chart']} — {it['why']}")
    table = {
        "title": "Machine snapshot",
        "columns": ["Metric", "Value"],
        "rows": [
            ["State", r["state"]],
            ["OEE", f"{r['oee']}%"],
            ["Availability", f"{r['avail']}%"],
            ["Performance", f"{r['perf']}%"],
            ["Quality", f"{r['qual']}%"],
            ["Health", f"{r['health']}%"],
            ["Temp", f"{r['temp']}°C"],
            ["Vibration", f"{r['vib']} mm/s"],
            ["Throughput", f"{r['thru']}/{r['target']}/h"],
        ],
    }
    follow = [i["label"] for i in INTENTS if i["id"] != intent][:3]
    return {
        "answer": " ".join(bits),
        "table": table,
        "charts": [{"intent": intent, "machine": r["id"]}],
        "follow_ups": follow,
        "mode": "fallback",
    }


def deterministic_analyze(machines: list, scn: dict | None) -> dict:
    """Rule-based Measure/Explain/Predict/Evaluate/Recommend narrative (grounded in scn)."""
    if not scn:
        return {"measure": "", "explain": "", "predict": "", "evaluate": "", "recommend": ""}
    tm = scn.get("targetMachine")
    alt = (scn.get("alternatives") or [{}])[0]
    losses = scn.get("losses") or []
    top = losses[0] if losses else {}
    return {
        "measure": (
            f"Line {scn.get('line')} ({tm}) has produced {scn.get('current')} of "
            f"{scn.get('target')} units; forecast {scn.get('forecastBase')} leaves a gap of "
            f"{scn.get('gap')} with {int(float(scn.get('attainBefore') or 0) * 100)}% attainment."
        ),
        "explain": (
            f"The largest loss is {top.get('type', 'material starvation')} "
            f"(~{top.get('units', 0)} units); micro-stops and reduced speed follow."
        ),
        "predict": (
            f"Without action the shift finishes near {scn.get('forecastBase')} units — "
            f"{abs(int(scn.get('gap') or 0))} short of target."
        ),
        "evaluate": (
            f"{len([a for a in scn.get('alternatives', []) if a.get('feasible')])} feasible "
            f"recovery actions were scored; the +8% speed option is blocked when machine "
            f"health is below the 0.70 operating limit."
        ),
        "recommend": (
            f"Recommended: {alt.get('type', 'prioritize material')} "
            f"(+{alt.get('recovered', 0)} units, {alt.get('risk', 'low')} risk)."
        ),
        "mode": "fallback",
    }


# ── prompt construction + parsing ─────────────────────────────────────────────

_ASK_SYSTEM = (
    "You are Minder, the AI analyst inside a manufacturing Optimize console. You answer questions "
    "about a live 20-machine fleet using ONLY the telemetry provided — never invent numbers. Keep "
    "the answer to 2-4 sentences of plain prose (no markdown tables). Then choose the single best "
    "chart to visualise the answer from this fixed taxonomy (the app draws it from live data — you "
    "only pick the intent id and machine id):\n"
    + "\n".join(f"- {it['id']}: {it['label']} ({it['chart']}) — {it['why']}" for it in INTENTS)
    + '\nReply with ONLY a JSON object: {"answer": str, "table": {"title": str, '
    '"columns": [str], "rows": [[str]]} | null, "charts": [{"intent": str, "machine": '
    '"M-NN"}], "follow_ups": [str]}. Use a compact table only when comparing values. Pick 1 '
    "chart (2 max). machine must be one of the ids in the data."
)

_ANALYZE_SYSTEM = (
    "You are Minder, the decision engine of a manufacturing Optimize console. A line will miss its "
    "shift target. Using ONLY the provided numbers (never invent), write a one-sentence narrative "
    "for each stage of the loop: measure, explain, predict, evaluate, recommend. Be concrete and "
    "cite the real figures. The recommendation must respect the machine-health operating limit "
    "(a speed increase is blocked when health < 0.70). Reply with ONLY a JSON object: "
    '{"measure": str, "explain": str, "predict": str, "evaluate": str, "recommend": str}.'
)


def _lang_suffix(lang: str | None) -> str:
    # Keep JSON keys English (so normalize_* still parses) but write the prose values in Vietnamese.
    return (
        "\nWrite all prose values in Vietnamese (Tieng Viet); keep the JSON keys in English."
        if lang == "vi"
        else ""
    )


def build_ask_messages(
    question: str, machines: list, scn: dict | None, lang: str | None = "en"
) -> tuple[str, str]:
    return _ASK_SYSTEM + _lang_suffix(lang), f"Question: {question}\n\n{fleet_context(machines, scn)}"


def build_analyze_messages(
    machines: list, scn: dict | None, lang: str | None = "en"
) -> tuple[str, str]:
    return _ANALYZE_SYSTEM + _lang_suffix(lang), fleet_context(machines, scn)


def parse_json(content: str) -> dict:
    """Extract the first JSON object from an LLM reply (tolerant of code fences / prose)."""
    if not content:
        raise ValueError("empty content")
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise ValueError("no JSON object in reply")
    return json.loads(m.group(0))


def normalize_ask(obj: dict, machines: list, scn: dict | None) -> dict:
    """Validate/repair an LLM Ask reply against the contract; backfill from the deterministic path."""
    ids = {str(m.get("id", "")).upper() for m in machines}
    answer = str(obj.get("answer") or "").strip()
    charts = []
    for c in (obj.get("charts") or [])[:2]:
        intent = c.get("intent")
        mid = str(c.get("machine", "")).upper()
        if intent in INTENT_IDS and mid in ids:
            charts.append({"intent": intent, "machine": mid})
    if not charts:  # fall back to a deterministic pick so the UI always has a chart
        fb = deterministic_ask(answer or "", machines, scn)
        charts = fb["charts"]
    table = obj.get("table") if isinstance(obj.get("table"), dict) else None
    follow = [str(x) for x in (obj.get("follow_ups") or [])][:4] or [
        i["label"] for i in INTENTS[:3]
    ]
    if not answer:
        answer = deterministic_ask("", machines, scn)["answer"]
    return {"answer": answer, "table": table, "charts": charts, "follow_ups": follow, "mode": "llm"}


def normalize_analyze(obj: dict, machines: list, scn: dict | None) -> dict:
    keys = ("measure", "explain", "predict", "evaluate", "recommend")
    fb = deterministic_analyze(machines, scn)
    out = {k: (str(obj.get(k)).strip() if obj.get(k) else fb.get(k, "")) for k in keys}
    out["mode"] = "llm"
    return out
