"""Warehouse microservice — the connector contract over the existing scripts.

ponytail: this service does NOT re-implement inventory logic. It shells out to
`modules/warehouse/scripts/inventory.py <action> --json`, exactly like Minder's
in-process /run route already does, so CLI and service outputs are identical by
construction. Move to in-process import only if per-request subprocess latency
ever measurably hurts.

Endpoints (the connector contract Minder + the React remote speak):
  GET  /connector/health          liveness
  GET  /connector/manifest        module info + agent tool specs + remoteEntry
  POST /connector/tools/{name}    agent tool call  {arguments} -> {success, output}
  POST /connector/run             dashboard action {action, args} -> result dict
  POST /connector/summarize       reverse call: ask Minder's LLM to summarize stock
  /dashboard/*                    the federated React remote (static build)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

SCRIPTS = Path(os.environ.get("WAREHOUSE_SCRIPTS", "/app/modules/warehouse/scripts"))
INVENTORY = SCRIPTS / "inventory.py"
DASHBOARD_DIST = Path(os.environ.get("DASHBOARD_DIST", "/svc/dashboard_dist"))
MINDER_API_BASE = os.environ.get("MINDER_API_BASE", "http://minder:8080").rstrip("/")
PUBLIC_BASE = os.environ.get("WAREHOUSE_PUBLIC_BASE", "http://localhost:8090").rstrip("/")
CORS_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o]

# Actions whose CLI subcommand does NOT declare --json (they print human text or
# already emit JSON). Everything else gets --json appended. Keep in sync with
# inventory.py's _build_parser.
_NO_JSON = {"snapshot", "move", "set-reorder", "remove", "reset", "export", "migrate"}
_JSON_OUT = {"snapshot"}  # emit machine JSON even without a --json flag

# Agent-facing tools (Minder calls these via /connector/tools/{name}). A focused,
# useful subset — add writes here when the agent needs them.
# ponytail: not every CLI subcommand is an agent tool; expose what earns its slot.
TOOLS: list[dict] = [
    {
        "name": "warehouse_snapshot",
        "action": "snapshot",
        "description": "Live inventory snapshot: KPIs, items, low/out-of-stock, recent sales.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "warehouse_low_stock",
        "action": "low-stock",
        "description": "List items at or below their reorder level (need restock).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "warehouse_query",
        "action": "query",
        "description": "Run a single read-only SELECT/WITH SQL query against the warehouse DB.",
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "one SELECT/WITH statement"}},
            "required": ["sql"],
        },
    },
    {
        "name": "warehouse_receive",
        "action": "receive",
        "description": "Receive stock for a SKU (positive movement).",
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "qty": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["sku", "qty"],
        },
    },
]
_ACTION_FOR_TOOL = {t["name"]: t["action"] for t in TOOLS}

app = FastAPI(title="warehouse-service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_flags(args: dict) -> list[str]:
    """Turn a JSON arg object into inventory.py CLI flags.

    key foo_bar / foo-bar -> --foo-bar; True -> bare flag; list -> repeated flag.
    """
    out: list[str] = []
    for key, value in (args or {}).items():
        flag = "--" + str(key).replace("_", "-")
        if value is True:
            out.append(flag)
        elif value is False or value is None:
            continue
        elif isinstance(value, (list, tuple)):
            for v in value:
                out += [flag, str(v)]
        else:
            out += [flag, str(value)]
    return out


def run_action(action: str, args: dict | None = None) -> dict:
    """Subprocess inventory.py; return its parsed JSON (or {stdout} for text cmds)."""
    if not INVENTORY.is_file():
        raise HTTPException(500, f"inventory.py not found at {INVENTORY}")
    argv = [sys.executable, str(INVENTORY), action, *_to_flags(args or {})]
    if action not in _NO_JSON:
        argv.append("--json")
    proc = subprocess.run(  # noqa: S603 — fixed interpreter + script, args are flags
        argv, cwd=str(SCRIPTS), capture_output=True, text=True, timeout=60
    )
    if proc.returncode != 0:
        raise HTTPException(400, (proc.stderr or proc.stdout or "action failed").strip())
    out = proc.stdout.strip()
    if action in _NO_JSON and action not in _JSON_OUT:
        return {"stdout": out}
    try:
        return json.loads(out) if out else {}
    except json.JSONDecodeError:
        return {"stdout": out}


# ── connector contract ────────────────────────────────────────────────────────


@app.get("/connector/health")
def health() -> dict:
    return {"ok": True, "module": "warehouse", "version": "1"}


@app.get("/connector/manifest")
def manifest() -> dict:
    return {
        "name": "warehouse",
        "display_name": "Warehouse",
        "tools": [
            {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
            for t in TOOLS
        ],
        "dashboard": {
            "remoteEntry": f"{PUBLIC_BASE}/dashboard/remoteEntry.js",
            "exposedModule": "warehouse/WarehouseDashboard",
            "api_base": PUBLIC_BASE,
        },
        "remote": True,
    }


class ToolBody(BaseModel):
    arguments: dict = Field(default_factory=dict)


@app.post("/connector/tools/{name}")
def call_tool(name: str, body: ToolBody) -> dict:
    action = _ACTION_FOR_TOOL.get(name)
    if action is None:
        raise HTTPException(404, f"unknown tool {name!r}")
    return {"success": True, "output": run_action(action, body.arguments)}


class RunBody(BaseModel):
    action: str = Field(min_length=1)
    args: dict = Field(default_factory=dict)


@app.post("/connector/run")
def run(body: RunBody) -> dict:
    return run_action(body.action, body.args)


class SummarizeBody(BaseModel):
    context_session_id: str | None = None


@app.post("/connector/summarize")
def summarize(body: SummarizeBody) -> dict:
    """Reverse connector: pull deterministic data locally, ask Minder's agent to
    summarize it. ponytail: inline httpx, no MinderClient class — the /chat route
    is a single ungated POST. Wrap in a client class only when a 2nd call site
    or auth appears."""
    snap = run_action("snapshot", {})
    kpis = snap.get("kpis") or snap.get("summary") or {}
    low = snap.get("low_stock") or snap.get("needs_restock") or []
    prompt = (
        "Summarize this warehouse inventory in 3 short bullets and flag restock "
        f"risks.\nKPIs: {json.dumps(kpis)}\nLow/at-reorder SKUs: {json.dumps(low)[:1500]}"
    )
    try:
        r = httpx.post(
            f"{MINDER_API_BASE}/api/modules/warehouse/chat",
            json={"message": prompt, "context_session_id": body.context_session_id},
            timeout=105,
        )
        r.raise_for_status()
        return {"summary": r.json().get("reply", "")}
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"minder chat unreachable: {exc}") from exc


# ── federated React remote (static build) ─────────────────────────────────────

if DASHBOARD_DIST.is_dir():
    app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIST), html=True), name="dashboard")
