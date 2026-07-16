"""FastAPI app factory for the generic workflow engine (unified app)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine import db
from engine.config.models import PrWorkflow
from engine.config.seed import seed_demo_workflow
from engine.routes import router


def _seed_if_empty() -> None:
    with db.db_session() as s:
        if not s.query(PrWorkflow).filter_by(key="demo").first():
            seed_demo_workflow(s)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        db.init_db()
        _seed_if_empty()
        yield

    app = FastAPI(title="Produce Workflow Engine", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
