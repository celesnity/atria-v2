"""maintenance_copilot connector service — the HTTP contract Atria speaks.

Endpoints:
  GET  /connector/health          liveness
  GET  /connector/manifest        module info + agent tool specs + remote entry
  POST /connector/tools/{name}    agent tool call → {success, output, card, llm_suffix}
  POST /connector/run             dashboard action {action, args} → result dict
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import service  # backend/service.py (pipeline dir already on sys.path via service import)

PUBLIC_BASE = os.environ.get("MC_PUBLIC_BASE", "http://localhost:9200").rstrip("/")
CORS_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o]

# Agent-facing tool specs. Mirrors the old in-process ToolSpec exactly.
TOOLS: list[dict] = [
    {
        "name": "maintenance_copilot_query",
        "description": (
            "Answer an aircraft-maintenance question (AMM/MEL/CDL/TSM/defect/dispatch/ATA) "
            "with grounded RAG: returns a cited, confidence-scored answer and renders it as "
            "a maintenance-answer card in the UI. Advisory only — never a dispatch decision."
        ),
        "parameters": {
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
    },
]

app = FastAPI(title="maintenance-copilot-service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/connector/health")
def health() -> dict:
    return {"ok": True, "module": "maintenance_copilot", "version": "1"}


@app.get("/connector/manifest")
def manifest() -> dict:
    return {
        "name": "maintenance_copilot",
        "display_name": "Maintenance Copilot",
        "tools": TOOLS,
        "remote": {
            "name": "maintenance_copilot",
            "remoteEntry": f"{PUBLIC_BASE}/dashboard/remoteEntry.js",
            "exposed": {
                "dashboard": "./Dashboard",
                "cards": {"maintenance_answer": "./MaintenanceAnswerCard"},
            },
        },
        "version": "1",
    }


class ToolBody(BaseModel):
    arguments: dict = Field(default_factory=dict)


@app.post("/connector/tools/{name}")
def call_tool(name: str, body: ToolBody) -> dict:
    if name != "maintenance_copilot_query":
        raise HTTPException(404, f"unknown tool {name!r}")
    args = body.arguments or {}
    text = (args.get("query") or args.get("text") or "").strip()
    if not text:
        return {"success": False, "output": "query is required", "card": None, "llm_suffix": None}
    try:
        card = service.run_query(
            text, int(args.get("k", 5)), args.get("ata"), args.get("revision", "current")
        )
        return {"success": True, "output": card, "card": card, "llm_suffix": None}
    except service.ServiceUnavailableError as exc:
        card = service.unavailable_payload(text, exc.service)
        suffix = service.UNAVAILABLE_SUFFIX.format(service=exc.service)
        return {"success": True, "output": card, "card": card, "llm_suffix": suffix}
    except Exception as exc:  # noqa: BLE001 — surface as tool error, never 500 the agent
        return {"success": False, "output": f"query failed: {exc}", "card": None, "llm_suffix": None}


class RunBody(BaseModel):
    action: str = Field(min_length=1)
    args: dict = Field(default_factory=dict)


# Dashboard actions (manifest.json activity: brief/usecases/validate/retrieve).
# 'retrieve' maps to a grounded query; the others are static views the frontend
# renders from its own state, so run() only needs the data-bearing one for now.
@app.post("/connector/run")
def run(body: RunBody) -> dict:
    if body.action == "retrieve":
        text = (body.args.get("query") or "").strip()
        if not text:
            raise HTTPException(400, "retrieve requires args.query")
        return service.run_query(text, int(body.args.get("k", 5)),
                                 body.args.get("ata"), body.args.get("revision", "current"))
    raise HTTPException(400, f"unsupported action {body.action!r}")
