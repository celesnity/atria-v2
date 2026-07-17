"""Connector service for the Optimize module — built on minder-python-sdk.

Optimize is the decision domain (brief §3.3/§3.4/§4): it READS the at-risk situation, runs the 6-stage
decision pipeline (read-only), and exposes RISK-GATED write actions that actuate the simulator. High-risk
writes return a decision packet and run only on human approval (the SDK gate); every accepted write emits
a domain event. This file never imports ``minder``; the engine lives in ``service.py`` (reusing the
module's ``scripts/``), so there is one source of truth shared with the ``blocks/guided.html`` tile.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from minder_python_sdk import Connector, card

import service

logger = logging.getLogger("optimize_demo")

conn = Connector(
    "optimize_demo",
    version="1",
    display_name="Optimize",
    public_base_env="OPTIMIZE_PUBLIC_BASE",
    dashboard_dist_env="OPTIMIZE_DASHBOARD_DIST",
    min_core_version="2",
    # Baseline autonomy: reads run freely; the high-risk actuations below need approval unless Core
    # raises the caller's autonomy to high/critical (mirrors the guided tile's approve-first gate).
    default_autonomy="medium",
)


# --- reads ---------------------------------------------------------------------
@conn.read(
    "optimize_situation",
    description="Read the current at-risk production scenario: the target machine, the shift gap, the "
    "forecast, the ranked recovery alternatives, and the constraint results.",
    when_to_use="Before recommending or acting — to see what is at risk right now.",
)
def optimize_situation(url: str | None = None, lang: str = "en") -> dict:
    return {"output": service.situation(url, lang)}


@conn.tool(
    "optimize_analyze",
    description="Run the whole operational decision loop over one live snapshot: Measure -> Explain -> "
    "Predict -> Evaluate -> Recommend. Returns a grounded per-stage envelope (observations / calculations "
    "/ findings / assumptions / confidence / data-quality) with a shared execution_id. Does NOT act.",
    read_only=True,  # a pure analysis — never gated
    card_type="optimize_analysis",
    when_to_use="When asked why the line is behind and what should be done, or for a full situation report.",
)
def optimize_analyze(url: str | None = None, lang: str = "en", execution_id: str | None = None) -> dict:
    result = service.analyze(url, lang, execution_id)
    rec = (result.get("recommend") or "")[:280]
    eid = (result.get("audit") or {}).get("execution_id") if isinstance(result.get("audit"), dict) else None
    conn.emit_event("recommendation.created", {"execution_id": eid, "summary": rec})
    return {"output": result, "card": card(rec or "Analysis complete.", card_type="optimize_analysis",
                                            confidence=0.8)}


# --- gated writes (actuate the simulator; high-risk -> decision packet + approval) ----
class ReleaseParams(BaseModel):
    count: int = Field(default=1, ge=1, le=20, description="How many product batches to release into intake.")
    product: str | None = Field(default=None, description="Product to release (default: top-supply product).")


@conn.tool(
    "optimize_release_product",
    description="Release product batches into the intake queue so starved washers resume. A real "
    "production change on the live plant.",
    params_model=ReleaseParams,
    risk="high",             # a production change -> requires human approval unless autonomy is raised
    reversible=False,
    undo="Released batches enter the intake queue and process; this cannot be un-released.",
    card_type="optimize_action",
    when_to_use="When the recommended action is to release product to relieve fleet starvation, and it "
    "has been approved.",
)
def optimize_release_product(count: int = 1, product: str | None = None, url: str | None = None) -> dict:
    res = service.release_product(count, product, url)
    ok = res.get("actuated")
    return {"output": res,
            "card": card(f"Released {res.get('count', count)}× {res.get('product', product) or 'product'} "
                         f"to intake." if ok else f"Release failed: {res.get('error', 'unknown')}.",
                         card_type="optimize_action", confidence=0.9 if ok else 0.3)}


class ServiceParams(BaseModel):
    machine_id: str = Field(description="The machine to full-service, e.g. 'M-08'.")


@conn.tool(
    "optimize_service_machine",
    description="Full-service a machine on the live plant: restores condition and un-trips a "
    "fault-stopped machine. A real maintenance actuation.",
    params_model=ServiceParams,
    risk="high",
    reversible=True,
    undo="Servicing only restores condition; re-injecting a fault would revert it (rarely wanted).",
    card_type="optimize_action",
    when_to_use="When the recommended action is to service/maintain a degraded or down machine, and it "
    "has been approved.",
)
def optimize_service_machine(machine_id: str, url: str | None = None) -> dict:
    res = service.service_machine(machine_id, url)
    ok = res.get("actuated")
    return {"output": res,
            "card": card(f"Serviced {res.get('machine', machine_id)}." if ok
                         else f"Service failed: {res.get('error', 'unknown')}.",
                         card_type="optimize_action", confidence=0.9 if ok else 0.3)}


# --- decision-context graph + events -------------------------------------------
@conn.graph
def optimize_graph(node=None, depth: int = 1):
    """Decision context: scenario -> target machine -> candidate actions."""
    return service.decision_graph(node, depth)


conn.event(
    "recommendation.created",
    description="Emitted when the decision loop produces a recommendation.",
    schema={"type": "object", "properties": {"execution_id": {"type": "string"}, "summary": {"type": "string"}}},
)


# --- health / readiness --------------------------------------------------------
@conn.health_probe
def _health() -> dict:
    return {"logic": "ok"}


@conn.readiness_probe
def _ready() -> dict:
    return {"fleet_sim": service.sim_reachable()}


app = conn.asgi()
