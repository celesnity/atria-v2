"""maintenance_copilot connector service — now built on atria-module-sdk.

The SDK generates the /connector/* contract (health, manifest, tool calls,
streaming, dashboard static mount) from the decorated handlers below; this file
never imports ``atria``. Domain specifics preserved from the hand-rolled version:

  * the tool returns a rich, strict-schema maintenance-answer card and names its
    UI renderer via ``card_type="maintenance_answer"`` (so the web UI keeps
    rendering the MaintenanceAnswerBlock, not the generic card);
  * a sidecar-down raises inside ``service.run_query`` and is converted here to
    the module's own fail-closed card + its corpus-specific LLM suffix;
  * dashboard ``/connector/run`` (retrieve), ``/connector/sidecar-health``, and
    the licensed-engineer ``/connector/signoff`` are registered as extra routes,
    reachable directly by the dashboard and through Atria's generic passthrough.
"""
from __future__ import annotations

from atria_module_sdk import Connector

import service  # backend/service.py (pipeline dir already on sys.path via service import)

# Keep the existing env-var names so docker-compose / the Dockerfile stay unchanged.
conn = Connector(
    "maintenance_copilot",
    version="1",
    display_name="Maintenance Copilot",
    public_base_env="MC_PUBLIC_BASE",
    dashboard_dist_env="MC_DASHBOARD_DIST",
)

_CARD_TYPE = "maintenance_answer"


@conn.tool(
    "maintenance_copilot_query",
    description=(
        "Answer an aircraft-maintenance question (AMM/MEL/CDL/TSM/defect/dispatch/ATA) "
        "with grounded RAG: returns a cited, confidence-scored answer and renders it as "
        "a maintenance-answer card in the UI. Advisory only — never a dispatch decision."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The maintenance question, in English."},
            "k": {"type": "integer", "default": 5, "description": "Passages to retrieve."},
            "ata": {"type": "string", "description": "Optional ATA chapter filter, e.g. '32'."},
            "revision": {"type": "string", "default": "current",
                         "description": "'current', a specific revision, or 'none'."},
        },
        "required": ["query"],
    },
    card_type=_CARD_TYPE,
)
def maintenance_copilot_query(query: str = "", k: int = 5, ata: str | None = None,
                              revision: str = "current", **kwargs) -> dict:
    text = (query or kwargs.get("text") or "").strip()
    if not text:
        return {"success": False, "output": "query is required", "card": None}
    try:
        card = service.run_query(text, int(k), ata, revision)
        return {"success": True, "output": card, "card": card, "card_type": _CARD_TYPE}
    except service.ServiceUnavailableError as exc:
        # Preserve the module's own strict-schema fail-closed card + corpus-specific
        # suffix (don't fall back to the SDK's generic ServiceUnavailable card).
        card = service.unavailable_payload(text, exc.service)
        suffix = service.UNAVAILABLE_SUFFIX.format(service=exc.service)
        return {"success": True, "output": card, "card": card,
                "card_type": _CARD_TYPE, "llm_suffix": suffix}


@conn.route("/run", methods=["POST"])
def run(body: dict) -> dict:
    """Dashboard action. Only the data-bearing 'retrieve' action needs the server;
    the other views render from the frontend's own state."""
    from fastapi import HTTPException

    action = (body or {}).get("action")
    args = (body or {}).get("args") or {}
    if action == "retrieve":
        text = (args.get("query") or "").strip()
        if not text:
            raise HTTPException(400, "retrieve requires args.query")
        return service.run_query(text, int(args.get("k", 5)),
                                 args.get("ata"), args.get("revision", "current"))
    raise HTTPException(400, f"unsupported action {action!r}")


@conn.route("/sidecar-health", methods=["GET"])
def sidecar_health() -> dict:
    """Probe the copilot sidecars (tei/llm/qdrant/neo4j)."""
    return service.sidecar_health()


@conn.route("/signoff", methods=["POST"])
def signoff(body: dict, principal) -> dict:
    """Record a licensed-engineer sign-off. The acting engineer comes from the
    forwarded Atria principal (X-Atria-Principal), not the request body."""
    payload = {"type": "signoff", "engineer": principal.username, **(body or {})}
    return {"ok": True, "event": service.record_signoff(payload)}


@conn.health_probe
def _liveness() -> dict:
    # Cheap liveness marker only; the heavy sidecar probes live at /sidecar-health
    # so /connector/health stays fast.
    return {"service": "ok"}


app = conn.asgi()
