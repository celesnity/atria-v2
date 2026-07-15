"""Produce Track B connector. Additive co-work surface over Track A services.
Imported ONLY when PR_AGENT_ENABLED; requires minder_python_sdk."""

from __future__ import annotations

import logging

from minder_python_sdk import Connector

logger = logging.getLogger("produce.agent")

conn = Connector(
    "produce",
    version="1",
    display_name="Produce",
    public_base_env="PR_PUBLIC_BASE",
    min_core_version="2",
    default_autonomy="medium",
)


def _wire_event_sink() -> None:
    """Forward emitted envelopes to Minder's event log (best-effort)."""
    try:
        client = conn.minder_client()
        conn.set_event_sink(client.emit_event)
    except Exception as exc:  # noqa: BLE001 — announce config may be absent in dev
        logger.warning("event sink not wired (announce config absent?): %s", exc)


def build_app():
    """Compose the connector ASGI with Track A routers + SPA attached.

    conn.asgi() owns the lifespan that runs announce/heartbeat, so it must be the
    top-level app (Starlette sub-app mounts do not run lifespans)."""
    import os

    import db
    from domain.config import routes as config_routes
    from domain.work import routes as work_routes
    from domain.sop import routes as sop_routes
    from domain.wip import routes as wip_routes
    from domain.downtime import routes as downtime_routes
    from domain.scrap import routes as scrap_routes
    from domain.oee import routes as oee_routes
    from domain.setup import routes as setup_routes
    from domain.handover import routes as handover_routes
    from domain.exception import routes as exception_routes
    from domain.report import routes as report_routes

    # Register the co-work surface on `conn` (import side effects).
    from agent import reads, events as agent_events, commands, guidance  # noqa: F401

    conn.on_startup(db.init_db)
    conn.on_startup(agent_events.attach)
    _wire_event_sink()

    app = conn.asgi(cors_origins=["*"])
    for mod in (
        config_routes, work_routes, sop_routes, wip_routes, downtime_routes,
        scrap_routes, oee_routes, setup_routes, handover_routes, exception_routes,
        report_routes,
    ):
        app.include_router(mod.router)

    from fastapi.staticfiles import StaticFiles

    dist = os.environ.get("PR_DASHBOARD_DIST", os.path.join(os.path.dirname(__file__), "..", "frontend_dist"))
    if os.path.isdir(dist):
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app
