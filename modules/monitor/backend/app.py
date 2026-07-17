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

from pydantic import BaseModel, Field

from minder_python_sdk import Connector, card

import service

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


# --- reads (risk="none", never gated) ------------------------------------------
@conn.read(
    "monitor_fleet",
    description="Read the live fleet: every machine's state/OEE/availability/health plus a fleet "
    "summary and the single at-risk scenario. The sensory snapshot other domains read from.",
    when_to_use="When you need the current state of the whole fleet, or fleet-level KPIs.",
)
def monitor_fleet(url: str | None = None, lang: str = "en") -> dict:
    status = service.fleet_status(url, lang)
    _emit_sensory_events(status)
    return {"output": status}


@conn.read(
    "monitor_machine",
    description="Read one machine's live telemetry (state, OEE, availability, health, temp, "
    "vibration, throughput vs target, downtime).",
    when_to_use="When the question is about a specific machine by id (e.g. M-08).",
)
def monitor_machine(machine_id: str, url: str | None = None, lang: str = "en") -> dict:
    return {"output": service.machine_detail(machine_id, url, lang)}


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
        "card": card(answer, card_type="monitor_answer",
                     confidence=0.9 if res.get("source") not in ("fallback", "error", "none") else 0.4),
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
    schema={"type": "object", "properties": {"machine": {"type": "string"}, "reason": {"type": "string"}}},
)
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
            conn.emit_event("machine.at_risk", {"machine": mid, "reason": m.get("reason") or "at_risk"})
        for mid in _last_at_risk - now:
            conn.emit_event("machine.recovered", {"machine": mid})
        _last_at_risk = now
    except Exception as exc:  # noqa: BLE001 — event emission must never break a read
        logger.warning("sensory event emit failed: %s", exc)


# --- health / readiness --------------------------------------------------------
@conn.health_probe
def _health() -> dict:
    return {"logic": "ok"}


@conn.readiness_probe
def _ready() -> dict:
    # Ready even if the sim is momentarily offline (reads fail-open with a banner); report the signal.
    return {"fleet_sim": service.sim_reachable()}


app = conn.asgi()
