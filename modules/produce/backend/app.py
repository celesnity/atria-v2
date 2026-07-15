"""Produce — Track A backend (phần mềm thuần, con người vận hành).

Plain FastAPI service: mỗi epic đóng góp một APIRouter human-facing. KHÔNG có
`@conn.tool`/AI ở đây — Track B (SDK) sẽ xếp chồng lên sau, không sửa Track A.

Thứ tự đăng ký bám critical path E11 → E1 → E3 → E4 → E6 → E8; các epic khác
nhánh ra hai bên.
"""

from __future__ import annotations

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI

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

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Produce", version="0.1.0", lifespan=lifespan)

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
