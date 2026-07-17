"""Pure business logic for the Optimize connector — never imports ``minder``.

Optimize is the decision domain: it reads the at-risk situation, runs the 6-stage decision pipeline, and
actuates the simulator through gated write actions. This file reuses the module's existing, self-contained
engine (``scripts/pipeline.py`` + ``simulate.py`` + ``ai.py`` + ``store.py``) so there is ONE source of
truth shared with the current ``blocks/guided.html`` tile; ``app.py`` shapes it into the SDK contract.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _cand in (_here.parents[1] / "scripts", _here.parent / "scripts"):
    if _cand.is_dir() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))
        break

import simulate  # noqa: E402
import ai  # noqa: E402


def _fleet_url(url: str | None) -> str | None:
    return url or os.environ.get("IIOT_FLEET_URL") or None


def situation(url: str | None = None, lang: str = "en") -> dict:
    """The current at-risk scenario + fleet summary (what the decision loop reasons over)."""
    payload = {"lang": lang}
    fu = _fleet_url(url)
    if fu:
        payload["url"] = fu
    status = simulate.handle_status(payload)
    return {
        "connected": status.get("connected"),
        "plant": status.get("plant"),
        "summary": status.get("summary"),
        "scn": status.get("scn"),
        "at_risk": (status.get("summary") or {}).get("at_risk_machine_ids"),
    }


def analyze(url: str | None = None, lang: str = "en", execution_id: str | None = None) -> dict:
    """Run the whole Measure -> Explain -> Predict -> Evaluate -> Recommend loop over one snapshot.

    Reuses ``ai.cmd_analyze`` (deterministic prose when no API key). Returns the flat per-stage envelope
    the guided tile / agent consume; ``audit.execution_id`` threads a coherent snapshot for follow-ups.
    """
    payload: dict = {"lang": lang}
    fu = _fleet_url(url)
    if fu:
        payload["fleet_url"] = fu
    if execution_id:
        payload["execution_id"] = execution_id
    return ai.cmd_analyze(payload)


def release_product(count: int = 1, product: str | None = None, url: str | None = None) -> dict:
    """Gated write: release product batches into the intake queue so starved washers resume.

    Actuates the REAL simulator (``/api/fleet/intake/release``) via the engine's release path.
    """
    payload: dict = {"action": "release", "count": int(count or 1)}
    if product:
        payload["product"] = product
    fu = _fleet_url(url)
    if fu:
        payload["url"] = fu
    return simulate.handle_actuate(payload)


def service_machine(machine_id: str, url: str | None = None) -> dict:
    """Gated write: full-service a machine (restores condition / un-trips a fault-stopped machine)."""
    payload: dict = {"action": "service", "machine": str(machine_id or "").strip().upper()}
    fu = _fleet_url(url)
    if fu:
        payload["url"] = fu
    return simulate.handle_actuate(payload)


def decision_graph(node: str | None = None, depth: int = 1, url: str | None = None) -> dict:
    """A small decision-context graph: scenario -> target machine -> alternatives."""
    sit = situation(url)
    scn = sit.get("scn") or {}
    tgt = scn.get("targetMachine") or scn.get("line") or "target"
    rec = scn.get("recId") or "scenario"
    nodes: list[dict] = [
        {"id": f"scenario:{rec}", "type": "scenario", "label": rec, "gap": scn.get("gap")},
        {"id": f"machine:{tgt}", "type": "machine", "label": tgt},
    ]
    edges: list[dict] = [{"from": f"scenario:{rec}", "to": f"machine:{tgt}", "rel": "targets"}]
    for a in scn.get("alternatives") or []:
        aid = f"action:{a.get('id')}"
        nodes.append({"id": aid, "type": "action", "label": a.get("type"),
                      "feasible": a.get("feasible"), "recovered": a.get("recovered"), "kind": a.get("kind")})
        edges.append({"from": f"machine:{tgt}", "to": aid, "rel": "candidate"})
    if node:
        keep = {node} | {e["to"] for e in edges if e["from"] == node} | {e["from"] for e in edges if e["to"] == node}
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges if e["from"] in keep and e["to"] in keep]
    return {"nodes": nodes, "edges": edges, "available": True}


def sim_reachable(url: str | None = None) -> bool:
    return bool(situation(url).get("connected"))
