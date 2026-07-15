"""Produce — Track A backend (phần mềm thuần, con người vận hành).

Plain FastAPI service: mỗi epic đóng góp một APIRouter human-facing. KHÔNG có
`@conn.tool`/AI ở đây — Track B (SDK) sẽ xếp chồng lên sau, không sửa Track A.

Thứ tự đăng ký bám critical path E11 → E1 → E3 → E4 → E6 → E8; các epic khác
nhánh ra hai bên.
"""

from __future__ import annotations

import logging
import os

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

logger = logging.getLogger("produce")


def _build_track_a_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        db.init_db()
        yield

    app = FastAPI(title="Produce", version="0.1.0", lifespan=lifespan)

    # Track A is standalone software; the UI (served from frontend_dist or a dev
    # vite server) is the only client. Permissive CORS keeps local dev simple.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # E11 nền tảng trước, rồi các epic phụ thuộc.
    for mod in (
        config_routes,
        work_routes,
        sop_routes,
        wip_routes,
        downtime_routes,
        scrap_routes,
        oee_routes,
        setup_routes,
        handover_routes,
        exception_routes,
        report_routes,
    ):
        app.include_router(mod.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "module": "produce"}

    # Serve the built React dashboard as a standalone SPA when it has been built
    # into ./frontend_dist (Docker copies it there). No-op in a bare checkout.
    _DIST = os.environ.get("PR_DASHBOARD_DIST", os.path.join(os.path.dirname(__file__), "frontend_dist"))
    if os.path.isdir(_DIST):
        app.mount("/", StaticFiles(directory=_DIST, html=True), name="ui")

    return app


_AGENT_ENABLED = os.environ.get("PR_AGENT_ENABLED", "0") not in ("", "0", "false", "False")

if _AGENT_ENABLED:
    from agent.connector import build_app

    app = build_app()
else:
    app = _build_track_a_app()
