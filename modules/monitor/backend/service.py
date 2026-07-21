"""Pure business logic for the Monitor connector — never imports ``minder``.

Monitor is the read/sensory domain: it reuses the module's existing, self-contained fleet logic
(``scripts/simulate.py`` + ``analysis.py`` + ``ai.py``) so there is ONE source of truth shared with the
current ``dashboard.html`` tile (which still calls the same scripts over the ``/run`` bridge). This file
only shapes that logic into plain dicts; ``app.py`` wraps these into the SDK ``/connector/*`` contract.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import json
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

OPERATIONS_CONTRACT = "monitor.operations.v1"
PRODUCE_CONTRACT = "monitor.produce.v1"
OPTIMIZE_CONTRACT = "monitor.optimize.v1"


def _fleet_url(url: str | None) -> str | None:
    return url or os.environ.get("IIOT_FLEET_URL") or None


def _base_url(url: str | None = None) -> str:
    return (_fleet_url(url) or getattr(simulate, "DEFAULT_URL", "http://127.0.0.1:5050")).rstrip(
        "/"
    )


def _get_json(path: str, url: str | None = None) -> dict:
    req = urllib.request.Request(_base_url(url) + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(
        req, timeout=float(os.environ.get("IIOT_FLEET_TIMEOUT", "3"))
    ) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        return {
            "ok": True,
            "connected": status.get("connected", False),
            "machine": None,
            "error": f"no machine {mid!r} in the fleet",
            "known": [m.get("id") for m in machines],
        }
    return {"ok": True, "connected": status.get("connected", False), "machine": match}


def ask(question: str, lang: str = "en", url: str | None = None) -> dict:
    """Grounded Q&A over the live fleet (gpt-5.4-mini via ``ai.cmd_ask``).

    Numbers are never invented: ``analysis.normalize_ask`` (inside ``cmd_ask``) forces the model to pick
    a machine + chart intent while the values come from the live snapshot; degrades deterministically on
    a missing key / network error. Returns ``{ok, answer, table, charts, follow_ups, source}``.
    """
    status = fleet_status(url, lang)
    return ai.cmd_ask(
        {
            "question": question,
            "machines": status.get("machines") or [],
            "scn": status.get("scn"),
            "lang": lang,
        }
    )


def _fallback_operational_snapshot(url: str | None = None) -> dict:
    """Compatibility snapshot when the simulator has not implemented the V2 seam."""
    fleet = fleet_status(url)
    machines = fleet.get("machines") or []
    target = machines[0] if machines else {}
    connected = bool(fleet.get("connected"))
    return {
        "contract_version": OPERATIONS_CONTRACT,
        "generated_at": fleet.get("ts"),
        "simulation_minute": fleet.get("simulation_minute", 0),
        "scenario": None,
        "run_id": fleet.get("run_id"),
        "scope": {
            "tenant_id": None,
            "plant_id": fleet.get("plant") if connected else None,
            "area_id": None,
            "line_id": target.get("cell") if connected else None,
            "station_id": target.get("assetTag") if connected else None,
            "machine_id": target.get("id"),
            "asset_tag": target.get("assetTag"),
            "timezone": "Asia/Bangkok",
        },
        "work_context": {},
        "source_health": {
            "source_id": "legacy-fleet-api",
            "status": "degraded" if connected else "disconnected",
            "connected": connected,
            "domain": fleet.get("domain"),
            "plant": fleet.get("plant"),
            "machine_count": len(machines),
            "run_id": fleet.get("run_id"),
            "source_url": _base_url(url),
            "quality": "uncertain" if connected else "bad",
            "latency_seconds": None,
            "clock_accuracy_ms": None,
            "calibration_status": "unknown",
            "warnings": ["Simulator V2 operations endpoint unavailable."],
        },
        "state": {
            "operating_state": target.get("state", "unknown"),
            "asset_condition": "unknown",
            "data_health": "incomplete" if connected else "disconnected",
            "operating_mode": "unknown",
        },
        "observations": [],
        "assets": machines,
        "intake": fleet.get("intake") or {},
        "summary": fleet.get("summary") or {},
    }


def operational_snapshot(url: str | None = None) -> dict:
    """Current canonical operational context with trust metadata."""
    try:
        return _get_json("/api/v2/operations/snapshot", url)
    except (OSError, ValueError, urllib.error.HTTPError):
        return _fallback_operational_snapshot(url)


def event_timeline(since_seq: int = 0, limit: int = 100, url: str | None = None) -> dict:
    """Versioned operational events, not raw alarm chatter."""
    query = urllib.parse.urlencode(
        {"since": max(0, int(since_seq)), "limit": max(1, min(int(limit), 500))}
    )
    try:
        return _get_json(f"/api/v2/operations/events?{query}", url)
    except (OSError, ValueError, urllib.error.HTTPError):
        snapshot = operational_snapshot(url)
        return {
            "contract_version": OPERATIONS_CONTRACT,
            "simulation_minute": snapshot.get("simulation_minute", 0),
            "scenario": snapshot.get("scenario"),
            "latest_seq": since_seq,
            "events": [],
            "warnings": ["Operational event endpoint unavailable."],
        }


def event_evidence(event_id: str, url: str | None = None) -> dict:
    """Evidence package for one operational event."""
    encoded = urllib.parse.quote(str(event_id or "").strip(), safe="")
    if not encoded:
        return {"error": "event_id is required", "event": None, "observations": []}
    try:
        return _get_json(f"/api/v2/operations/events/{encoded}/evidence", url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "error": f"unknown operational event {event_id!r}",
                "event": None,
                "observations": [],
            }
        raise
    except (OSError, ValueError):
        return {
            "error": "operational evidence endpoint unavailable",
            "event": None,
            "observations": [],
        }


def source_health(url: str | None = None) -> dict:
    snapshot = operational_snapshot(url)
    health = dict(snapshot.get("source_health") or {})
    return {
        "contract_version": OPERATIONS_CONTRACT,
        "generated_at": snapshot.get("generated_at"),
        "overall_status": health.get("status", "unknown"),
        "sources": [health],
        "data_health": (snapshot.get("state") or {}).get("data_health", "unknown"),
    }


def _consumer_events(consumer: str, url: str | None = None) -> tuple[dict, list[dict]]:
    timeline = event_timeline(0, 500, url)
    events = [
        event
        for event in timeline.get("events") or []
        if consumer in (event.get("consumers") or [])
    ]
    return timeline, events


def produce_data_product(url: str | None = None) -> dict:
    """Purpose-built facts Produce may consume without interpreting raw sensor tags."""
    snapshot = operational_snapshot(url)
    timeline, events = _consumer_events("produce", url)
    candidate_types = {
        "micro_stop_detected",
        "material_starvation_detected",
        "product_starvation_detected",
        "downstream_blockage_detected",
    }
    cycle_types = {"production_cycle_started", "production_cycle_completed"}
    return {
        "contract_version": PRODUCE_CONTRACT,
        "generated_at": snapshot.get("generated_at"),
        "scope": snapshot.get("scope") or {},
        "work_context": snapshot.get("work_context") or {},
        "equipment_state": snapshot.get("state") or {},
        "assets": snapshot.get("assets") or [],
        "intake": snapshot.get("intake") or {},
        "downtime_candidates": [
            event for event in events if event.get("event_type") in candidate_types
        ],
        "cycle_events": [event for event in events if event.get("event_type") in cycle_types],
        "facts": events,
        "source_health": snapshot.get("source_health") or {},
        "data_quality": {
            "status": (snapshot.get("state") or {}).get("data_health", "unknown"),
            "warnings": timeline.get("warnings") or [],
            "conflicts": snapshot.get("conflicts") or [],
        },
        "provenance": {
            "source_contract": snapshot.get("contract_version"),
            "latest_event_sequence": timeline.get("latest_seq", 0),
            "fact_labels": sorted(
                {event.get("fact_label") for event in events if event.get("fact_label")}
            ),
        },
    }


def optimize_data_product(url: str | None = None) -> dict:
    """Purpose-built state, losses, constraints, and outcomes for Optimize."""
    snapshot = operational_snapshot(url)
    fleet = fleet_status(url)
    timeline, events = _consumer_events("optimize", url)
    losses = [
        event
        for event in events
        if event.get("event_type")
        in {"production_loss_event", "normalized_downtime_event", "micro_stop_detected"}
    ]
    constraints = [
        event
        for event in events
        if event.get("event_type")
        in {
            "material_starvation_detected",
            "product_starvation_detected",
            "constraint_state_changed",
            "bottleneck_state_changed",
        }
    ]
    invalidations = [
        event for event in events if event.get("event_type") == "recommendation_invalidating_event"
    ]
    outcomes = [
        event for event in events if event.get("event_type") == "intervention_outcome_recorded"
    ]
    summary = fleet.get("summary") or {}
    return {
        "contract_version": OPTIMIZE_CONTRACT,
        "generated_at": snapshot.get("generated_at"),
        "scope": snapshot.get("scope") or {},
        "work_context": snapshot.get("work_context") or {},
        "operational_state_snapshot": {
            "state": snapshot.get("state") or {},
            "average_oee": summary.get("average_oee"),
            "total_throughput_per_hour": summary.get("total_throughput_per_hour"),
            "total_target_per_hour": summary.get("total_target_per_hour"),
            "completed_batches": summary.get("batches_completed"),
        },
        "assets": snapshot.get("assets") or [],
        "intake": snapshot.get("intake") or {},
        "production_loss_events": losses,
        "constraints": constraints,
        "recommendation_invalidating_events": invalidations,
        "intervention_outcomes": outcomes,
        "data_readiness": {
            "status": (snapshot.get("state") or {}).get("data_health", "unknown"),
            "source_quality": (snapshot.get("source_health") or {}).get("quality", "unknown"),
            "freshness_seconds": (snapshot.get("source_health") or {}).get("latency_seconds"),
            "identity_complete": bool(
                (snapshot.get("scope") or {}).get("plant_id")
                and all(
                    asset.get("id") and asset.get("asset_tag")
                    for asset in (snapshot.get("assets") or [])
                )
            ),
            "warnings": timeline.get("warnings") or [],
            "conflicts": snapshot.get("conflicts") or [],
        },
        "provenance": {
            "source_contract": snapshot.get("contract_version"),
            "latest_event_sequence": timeline.get("latest_seq", 0),
            "source_event_ids": [event.get("event_id") for event in events],
        },
    }


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
        nodes.append(
            {
                "id": mnode,
                "type": "machine",
                "label": mid,
                "state": m.get("state"),
                "oee": m.get("oee"),
                "health": m.get("health"),
            }
        )
        edges.append({"from": line_id, "to": mnode, "rel": "contains"})
        if m.get("state") == "down" or m.get("atRisk") or (m.get("warnings") or []):
            anode = f"alarm:{mid}"
            reason = m.get("reason") or ("at_risk" if m.get("atRisk") else "warning")
            nodes.append({"id": anode, "type": "alarm", "label": reason, "machine": mid})
            edges.append({"from": mnode, "to": anode, "rel": "raises"})
    if node:
        keep = (
            {node}
            | {e["to"] for e in edges if e["from"] == node}
            | {e["from"] for e in edges if e["to"] == node}
        )
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
