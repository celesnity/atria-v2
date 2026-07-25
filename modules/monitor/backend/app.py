"""Connector service for the Monitor module — built on minder-python-sdk.

Monitor is the read/sensory domain (brief §2.2, §11.1): it senses the fleet in real time and is the
substrate other domains read from. It exposes READ tools (never gated), a grounded Ask-AI, an
Operational-Graph provider, and sensory domain events — but NO write/actuation (that is Optimize).

The SDK generates the whole ``/connector/*`` contract from the decorated handlers below; this file
never imports ``minder``. Reused fleet logic lives in ``service.py`` (which wraps the module's existing
``scripts/``), so there is one source of truth shared with the current ``dashboard.html`` tile.
"""

from __future__ import annotations

import logging
import os
import time

from pydantic import BaseModel, Field

from minder_python_sdk import Connector, Response, ToolError, card

import service
from models import (
    EventTimelineResult,
    EvidenceResult,
    OperationalSnapshotResult,
    OptimizeDataProductResult,
    ProduceDataProductResult,
    SourceHealthResult,
)

logger = logging.getLogger("monitor")

conn = Connector(
    "monitor",
    version="1",
    display_name="Monitor",
    public_base_env="MONITOR_PUBLIC_BASE",
    dashboard_dist_env="MONITOR_DASHBOARD_DIST",
    min_core_version="2",
    # Read-only sensory domain — reads are never gated regardless; a high baseline means the (absent)
    # write path would not surprise-gate either.
    default_autonomy="high",
)

# In-memory sensory state so we only emit a machine event on a real transition (this is a long-lived
# process, so remembering the last at-risk set across reads is honest, not fabricated).
_last_at_risk: set[str] = set()
_last_operational_seq = 0
_last_operational_run_id: str | None = None


# --- reads (risk="none", never gated) ------------------------------------------
@conn.read(
    "monitor_fleet",
    description="Read the live fleet: every machine's state/OEE/availability/health plus a fleet "
    "summary and the single at-risk scenario. The sensory snapshot other domains read from.",
    when_to_use="When you need the current state of the whole fleet, or fleet-level KPIs.",
)
def monitor_fleet(url: str | None = None, lang: str = "en") -> dict:
    status = service.fleet_status(url, lang)
    return {"output": status}


@conn.read(
    "monitor_machine",
    description="Read one machine's live telemetry (state, OEE, availability, health, temp, "
    "vibration, throughput vs target, downtime).",
    when_to_use="When the question is about a specific machine by id (e.g. M-08).",
)
def monitor_machine(machine_id: str, url: str | None = None, lang: str = "en") -> dict:
    result = service.machine_detail(machine_id, url, lang)
    if result.get("machine") is None:
        raise ToolError(
            "unknown_machine", result.get("error") or "unknown machine", retryable=False
        )
    return {"output": result}


@conn.read(
    "monitor_live_operations",
    description="Read the canonical operational context: identity, work context, separate operating/asset/data states, trustworthy observations, and source health.",
    when_to_use="For the current line/station truth before inspecting events or consumer data products.",
)
def monitor_live_operations(url: str | None = None) -> OperationalSnapshotResult:
    result = OperationalSnapshotResult.model_validate(service.operational_snapshot(url))
    return Response(result=result.model_dump())


class TimelineParams(BaseModel):
    since_seq: int = Field(default=0, ge=0, description="Return events after this sequence cursor.")
    limit: int = Field(default=100, ge=1, le=500)


@conn.read(
    "monitor_event_timeline",
    description="Read deduplicated, contextual operational facts with evidence, provenance, semantic labels, and consumer routing.",
    params_model=TimelineParams,
    when_to_use="To understand what changed and in which order, without reading raw alarm chatter.",
)
def monitor_event_timeline(
    since_seq: int = 0, limit: int = 100, url: str | None = None
) -> EventTimelineResult:
    result = EventTimelineResult.model_validate(service.event_timeline(since_seq, limit, url))
    return Response(result=result.model_dump())


class EvidenceParams(BaseModel):
    event_id: str = Field(description="Operational event id, for example MON-V1-0007.")


@conn.read(
    "monitor_event_evidence",
    description="Read the complete evidence package for one operational fact, including source observations, health, conflicts, and provenance.",
    params_model=EvidenceParams,
    when_to_use="Before trusting, confirming, or explaining an operational event.",
)
def monitor_event_evidence(event_id: str, url: str | None = None) -> EvidenceResult:
    result = service.event_evidence(event_id, url)
    if result.get("event") is None:
        raise ToolError("unknown_event", result.get("error") or "unknown event", retryable=False)
    return Response(result=EvidenceResult.model_validate(result).model_dump())


@conn.read(
    "monitor_source_health",
    description="Read source connection, freshness, clock accuracy, quality, calibration, and overall data health.",
    when_to_use="Before using Monitor facts when source freshness or trust may be uncertain.",
)
def monitor_source_health(url: str | None = None) -> SourceHealthResult:
    result = SourceHealthResult.model_validate(service.source_health(url))
    return Response(result=result.model_dump())


@conn.read(
    "monitor_produce_data_product",
    description="Read Produce-ready equipment state, cycle facts, downtime candidates, evidence, data quality, and work identity. No production record is changed.",
    when_to_use="When Produce or an operator workflow needs contextualized machine facts without interpreting raw tags.",
)
def monitor_produce_data_product(url: str | None = None) -> ProduceDataProductResult:
    result = ProduceDataProductResult.model_validate(service.produce_data_product(url))
    return Response(result=result.model_dump())


@conn.read(
    "monitor_optimize_data_product",
    description="Read Optimize-ready operational state, normalized loss signals, live constraints, invalidating events, outcomes, readiness, and provenance.",
    when_to_use="Before measuring a loss, evaluating a recommendation, or validating an intervention outcome.",
)
def monitor_optimize_data_product(url: str | None = None) -> OptimizeDataProductResult:
    result = OptimizeDataProductResult.model_validate(service.optimize_data_product(url))
    return Response(result=result.model_dump())


# --- Ask-AI (read-only tool: a carded, grounded answer) ------------------------
class AskParams(BaseModel):
    question: str = Field(description="A natural-language question about a machine or the fleet.")
    lang: str = Field(default="en", description="'en' or 'vi'.")


@conn.tool(
    "monitor_ask",
    description="Answer a natural-language question about the fleet, grounded in live data, and pick "
    "the best-fit chart. The model writes prose + picks a machine/chart intent; the numbers always "
    "come from the live snapshot (it never invents them).",
    params_model=AskParams,
    read_only=True,  # forces risk='none' — a pure grounded query, never gated
    card_type="monitor_answer",
    when_to_use="For any free-text question about machine/fleet status when a short written answer "
    "(optionally with a chart) is wanted.",
    examples=[{"question": "Why is M-08 down?"}, {"question": "How is the fleet doing right now?"}],
)
def monitor_ask(question: str, lang: str = "en", url: str | None = None) -> dict:
    res = service.ask(question, lang=lang, url=url)
    answer = res.get("answer") or ""
    return {
        "output": res,
        "card": card(
            answer,
            card_type="monitor_answer",
            confidence=0.9 if res.get("source") not in ("fallback", "error", "none") else 0.4,
        ),
    }


# --- Operational Graph (Monitor is the sensory substrate) ----------------------
@conn.graph
def fleet_graph(node=None, depth: int = 1):
    """Linked context over the fleet: plant → line → machine → alarm. Ask for a node
    (e.g. ``machine:M-08``) for its neighbourhood, or omit ``node`` for the whole graph."""
    return service.fleet_graph(node, depth)


# --- sensory domain events -----------------------------------------------------
conn.event(
    "machine.at_risk",
    description="Emitted when a machine transitions into a down/at-risk state.",
    schema={
        "type": "object",
        "properties": {"machine": {"type": "string"}, "reason": {"type": "string"}},
    },
)

_OPERATIONAL_EVENT_TYPES = {
    "production_context_started": "A production work context became active.",
    "production_cycle_completed": "A contextualized production cycle completed.",
    "production_cycle_started": "A contextualized production cycle started.",
    "micro_stop_detected": "A short no-fault stop was detected.",
    "equipment_state_changed": "Equipment changed operational state.",
    "material_starvation_detected": "Evidence indicates the station is material-starved.",
    "product_starvation_detected": "Evidence indicates washers are waiting for product.",
    "production_loss_event": "A calculated production loss is accumulating.",
    "asset_condition_changed": "Observed asset condition evidence changed.",
    "quality_risk_updated": "Observed process or outcome evidence changed quality risk.",
    "intervention_outcome_recorded": "An observed intervention outcome window is ready.",
    "source_health_changed": "A telemetry source changed trust or availability state.",
    "constraint_state_changed": "An Optimize-relevant live constraint changed.",
    "recommendation_invalidating_event": "Live state invalidated an active recommendation.",
}
_EVENT_SCHEMA = {
    "type": "object",
    "required": [
        "event_id",
        "sequence",
        "event_type",
        "occurred_at",
        "scope",
        "fact_label",
        "consumers",
    ],
    "properties": {
        "event_id": {"type": "string"},
        "sequence": {"type": "integer"},
        "event_type": {"type": "string"},
        "occurred_at": {"type": "string", "format": "date-time"},
        "scope": {"type": "object"},
        "work_context": {"type": "object"},
        "fact_label": {"type": "string"},
        "consumers": {"type": "array", "items": {"type": "string"}},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "provenance": {"type": "object"},
    },
}
for _event_type, _description in _OPERATIONAL_EVENT_TYPES.items():
    conn.event(_event_type, description=_description, schema=_EVENT_SCHEMA)


for _page_id, _label, _description in (
    ("live_operations", "Live Operations", "Current operational state and active facts."),
    ("event_timeline", "Event Timeline", "Ordered events and evidence."),
    ("assets", "Assets", "Machine and sensor drill-down."),
    ("data_health", "Data Health", "Freshness, quality, clock, and calibration."),
    ("data_products", "Data Products", "Produce and Optimize consumer contracts."),
):
    conn.page(_page_id, path=f"/{_page_id}", label=_label, description=_description)

conn.context.knowledge(
    "Monitor is a read-only sensory module. It labels observed, calculated, and inferred facts; "
    "it never modifies production records or actuates equipment."
)
conn.context.note(
    "produce", "Use monitor_produce_data_product for equipment state and downtime candidates."
)
conn.context.note(
    "optimize",
    "Use monitor_optimize_data_product for losses, constraints, readiness, and outcomes.",
)


@conn.context.state("data_readiness", "Current Monitor source and data health.")
def _data_readiness_state() -> dict:
    return service.source_health()


conn.event(
    "machine.recovered",
    description="Emitted when a machine transitions out of a down/at-risk state.",
    schema={"type": "object", "properties": {"machine": {"type": "string"}}},
)


def _emit_sensory_events(status: dict) -> None:
    """Emit machine.at_risk / machine.recovered only on a real transition vs the last read."""
    global _last_at_risk
    try:
        now = service.at_risk_ids(status)
        by_id = {str(m.get("id")): m for m in (status.get("machines") or [])}
        for mid in now - _last_at_risk:
            m = by_id.get(mid, {})
            conn.emit_event(
                "machine.at_risk", {"machine": mid, "reason": m.get("reason") or "at_risk"}
            )
        for mid in _last_at_risk - now:
            conn.emit_event("machine.recovered", {"machine": mid})
        _last_at_risk = now
    except Exception as exc:  # noqa: BLE001 — event emission must never break a read
        logger.warning("sensory event emit failed: %s", exc)


def _poll_once() -> int:
    """Publish unseen simulator facts to the SDK event stream; safe to call in tests."""
    global _last_operational_seq, _last_operational_run_id
    _emit_sensory_events(service.fleet_status())
    timeline = service.event_timeline(_last_operational_seq, 500)
    run_id = timeline.get("run_id")
    if (_last_operational_run_id is not None and run_id != _last_operational_run_id) or int(
        timeline.get("latest_seq") or 0
    ) < _last_operational_seq:
        # A deterministic simulator replay resets its sequence. Re-read from zero so the
        # event stream represents the new run instead of silently suppressing it.
        _last_operational_seq = 0
        timeline = service.event_timeline(0, 500)
    _last_operational_run_id = timeline.get("run_id")
    for event in timeline.get("events") or []:
        event_type = event.get("event_type")
        if event_type in _OPERATIONAL_EVENT_TYPES:
            conn.emit_event(event_type, event, source="module")
        _last_operational_seq = max(_last_operational_seq, int(event.get("sequence") or 0))
    return _last_operational_seq


@conn.on_startup
def _start_event_poller() -> None:
    interval = float(os.environ.get("MONITOR_EVENT_POLL_SEC", "4"))
    if interval <= 0:
        return
    while True:
        try:
            _poll_once()
        except Exception as exc:  # noqa: BLE001 - telemetry outage must not stop the connector
            logger.warning("operational event poll failed: %s", exc)
        time.sleep(interval)


# --- health / readiness --------------------------------------------------------
@conn.health_probe
def _health() -> dict:
    return {"logic": "ok"}


@conn.readiness_probe
def _ready() -> dict:
    # Ready even if the sim is momentarily offline (reads fail-open with a banner); report the signal.
    return {"fleet_sim": service.sim_reachable()}


_connector_app = conn.asgi()


async def app(scope, receive, send):
    """Expose the stack-wide health contract without changing the SDK contract."""
    if scope["type"] == "http" and scope.get("path") == "/health":
        from starlette.responses import JSONResponse

        ready = service.sim_reachable()
        response = JSONResponse(
            {
                "service": "atria-monitor",
                "status": "ok" if ready else "degraded",
                "ready": ready,
                "dependencies": [{"name": "iotmock-laundry", "required": True, "ready": ready}],
                "capabilities": ["fleet-insight", "operational-evidence", "read-only"],
            },
            status_code=200 if ready else 503,
        )
        await response(scope, receive, send)
        return
    await _connector_app(scope, receive, send)
