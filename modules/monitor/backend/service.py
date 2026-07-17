"""Pure business logic for the Monitor connector — never imports ``minder``.

Monitor is the read/sensory domain: it reuses the module's existing, self-contained fleet logic
(``scripts/simulate.py`` + ``analysis.py`` + ``ai.py``) so there is ONE source of truth shared with the
current ``dashboard.html`` tile (which still calls the same scripts over the ``/run`` bridge). This file
only shapes that logic into plain dicts; ``app.py`` wraps these into the SDK ``/connector/*`` contract.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Put the module's ``scripts/`` on the path so we can reuse simulate/analysis/ai flat (ai.py already
# falls back from ``from . import`` to a flat import). Works in dev (``modules/monitor/scripts``, i.e.
# parents[1]/scripts) and in the container image (scripts copied next to the backend → ./scripts).
_here = Path(__file__).resolve()
for _cand in (_here.parents[1] / "scripts", _here.parent / "scripts"):
    if _cand.is_dir() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))
        break

import simulate  # noqa: E402  (path set above)
import ai  # noqa: E402


def _fleet_url(url: str | None) -> str | None:
    return url or os.environ.get("IIOT_FLEET_URL") or None


def fleet_status(url: str | None = None, lang: str = "en") -> dict:
    """The live fleet: KPIs-worthy machine list + summary + a single fleet-context ``scn``.

    Reuses ``simulate.handle_status`` verbatim (stdlib-only, fail-open when the sim is offline).
    """
    payload = {"lang": lang}
    fu = _fleet_url(url)
    if fu:
        payload["url"] = fu
    return simulate.handle_status(payload)


def machine_detail(machine_id: str, url: str | None = None, lang: str = "en") -> dict:
    """One machine's live telemetry, pulled from the fleet snapshot."""
    mid = str(machine_id or "").strip().upper()
    status = fleet_status(url, lang)
    machines = status.get("machines") or []
    match = next((m for m in machines if str(m.get("id", "")).upper() == mid), None)
    if match is None:
        return {"ok": True, "connected": status.get("connected", False), "machine": None,
                "error": f"no machine {mid!r} in the fleet",
                "known": [m.get("id") for m in machines]}
    return {"ok": True, "connected": status.get("connected", False), "machine": match}


def ask(question: str, lang: str = "en", url: str | None = None) -> dict:
    """Grounded Q&A over the live fleet (gpt-5.4-mini via ``ai.cmd_ask``).

    Numbers are never invented: ``analysis.normalize_ask`` (inside ``cmd_ask``) forces the model to pick
    a machine + chart intent while the values come from the live snapshot; degrades deterministically on
    a missing key / network error. Returns ``{ok, answer, table, charts, follow_ups, source}``.
    """
    status = fleet_status(url, lang)
    return ai.cmd_ask({
        "question": question,
        "machines": status.get("machines") or [],
        "scn": status.get("scn"),
        "lang": lang,
    })


def fleet_graph(node: str | None = None, depth: int = 1, url: str | None = None) -> dict:
    """The Operational Graph slice Monitor owns: plant → line(cell) → machine → alarm.

    Monitor is the sensory substrate other domains read (brief §2.2). Nodes are typed
    (``plant:`` / ``line:`` / ``machine:`` / ``alarm:``); ``node`` narrows to a neighbourhood.
    """
    status = fleet_status(url)
    machines = status.get("machines") or []
    plant = status.get("plant") or "plant"
    nodes: list[dict] = [{"id": "plant:root", "type": "plant", "label": plant}]
    edges: list[dict] = []
    seen_lines: set[str] = set()
    for m in machines:
        mid = m.get("id")
        cell = m.get("cell") or "line"
        line_id = f"line:{cell}"
        if line_id not in seen_lines:
            seen_lines.add(line_id)
            nodes.append({"id": line_id, "type": "line", "label": cell})
            edges.append({"from": "plant:root", "to": line_id, "rel": "contains"})
        mnode = f"machine:{mid}"
        nodes.append({"id": mnode, "type": "machine", "label": mid,
                      "state": m.get("state"), "oee": m.get("oee"), "health": m.get("health")})
        edges.append({"from": line_id, "to": mnode, "rel": "contains"})
        if m.get("state") == "down" or m.get("atRisk") or (m.get("warnings") or []):
            anode = f"alarm:{mid}"
            reason = m.get("reason") or ("at_risk" if m.get("atRisk") else "warning")
            nodes.append({"id": anode, "type": "alarm", "label": reason, "machine": mid})
            edges.append({"from": mnode, "to": anode, "rel": "raises"})
    if node:
        keep = {node} | {e["to"] for e in edges if e["from"] == node} | {e["from"] for e in edges if e["to"] == node}
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges if e["from"] in keep and e["to"] in keep]
    return {"nodes": nodes, "edges": edges, "available": True}


def at_risk_ids(status: dict) -> set[str]:
    """The set of machine ids currently down or at-risk — the sensory signal Monitor emits events for."""
    out: set[str] = set()
    for m in status.get("machines") or []:
        if m.get("state") == "down" or m.get("atRisk"):
            out.add(str(m.get("id")))
    return out


def sim_reachable(url: str | None = None) -> bool:
    """Readiness: can we reach the fleet simulator right now?"""
    return bool(fleet_status(url).get("connected"))
