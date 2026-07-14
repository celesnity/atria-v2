# Service-Module Federation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract `maintenance_copilot` from Minder's in-process module system into a self-contained, containerized service-module (own deps, own backend, own federated React frontend), leaving Minder to talk to it only over an HTTP connector contract and Module Federation.

**Architecture:** A *service-module* is a full-stack folder under `modules/<name>/` with a `backend/` (FastAPI connector, own `requirements.txt` + `Dockerfile`, own container) and a `frontend/` (Vite Module Federation remote). Minder core stops importing the module's Python; it registers **proxy tools** from the module's committed manifest that HTTP-call the connector at run time, re-broadcasting the module's structured card to the UI. The web UI host loads the module's dashboard as a runtime-registered federation remote, rendered natively in-host (no iframe). Built backend-first across 4 phases so the dependency-isolation win lands and is verifiable before the federation frontend.

**Tech Stack:** Python 3.12 + FastAPI + httpx (backend & Minder consumer), pydantic; React 18 + Vite 5 + `@module-federation/vite` + `@module-federation/runtime` (frontend); Docker Compose (orchestration); pytest + Vitest (tests).

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-09-service-module-federation-design.md` — this plan implements it.
- **Boundary rule:** Minder core and the service communicate ONLY over HTTP (connector) + Module Federation (UI). No Python import may cross the boundary — after Phase 1, nothing in `minder/` imports `openai`, `qdrant-client`, `neo4j`, or `chonkie` on behalf of this module.
- **Heavy deps stay service-side:** `openai>=1.40`, `qdrant-client>=1.11`, `neo4j>=5.24`, `chonkie>=1.0` live only in `modules/maintenance_copilot/backend/requirements.txt`, never in the Minder image.
- **Preserve behavior:** the agent tool name stays exactly `maintenance_copilot_query`; the UI card broadcast stays exactly `{"type": "maintenance_answer", ...}`; the guardrail (no direct `sample_manuals` reads; the `_llm_suffix` no-freelancing directive) is preserved; a down sidecar/service returns a structured "unavailable" card, never a crash and never freelancing.
- **Connector URL split:** Minder's server-side proxy tool calls the connector over the Docker network (`http://maintenance-copilot:9200`); the browser loads the federation remote over a public URL (`http://localhost:9200`). Never conflate them.
- **Python style:** line length 100 (Black + Ruff), type hints on public APIs (mypy strict), Google-style docstrings.
- **Test command:** `uv run --no-sync pytest <path>` for Python; `pnpm --dir web-ui test` for web-ui (Vitest). Do NOT use bare `pytest`.
- **Compose service name:** `maintenance-copilot` (hyphen); container port `9200`.
- **User workflow note:** per the user's stated preference, per-step test *execution* may be batched — implement the code, then run the phase's tests together at the end of the phase — but the test code itself must still be written first (test-first) as each task specifies. Do not skip writing tests.
- **Commits:** no `Co-Authored-By: Claude` trailer.

---

## File Structure

**Created (module — service side):**
- `modules/maintenance_copilot/backend/pipeline/` — the current `scripts/*.py`, moved verbatim.
- `modules/maintenance_copilot/backend/sample_manuals/` — the RAG corpus, moved.
- `modules/maintenance_copilot/backend/service.py` — pure pipeline entry: `run_query()` + `unavailable_payload()` (the brains of today's `tools.py`, minus the Minder import).
- `modules/maintenance_copilot/backend/app.py` — FastAPI connector contract.
- `modules/maintenance_copilot/backend/requirements.txt` — heavy deps.
- `modules/maintenance_copilot/backend/Dockerfile` — service image.
- `modules/maintenance_copilot/frontend/` — Vite MF remote (`package.json`, `vite.config.ts`, `src/DashboardApp.tsx`).

**Created (Minder — consumer side):**
- `minder/core/modules/remote.py` — `RemoteConnector` HTTP client + `build_remote_tool_specs()`.
- `web-ui/src/lib/federation.ts` — runtime remote registration + component loader.
- `tests/test_connector_app.py`, `tests/test_remote_connector.py`, `tests/test_module_service_manifest.py` — Python tests.

**Modified:**
- `modules/maintenance_copilot/manifest.json` — add `service` + `remote` blocks.
- `modules/maintenance_copilot/SKILL.md` — remove `tools: tools.py` (Minder no longer loads it).
- `modules/maintenance_copilot/tools.py`, `scripts/`, `requirements.txt`, `dashboard.html` — deleted from the Minder-loaded surface.
- `minder/core/modules/store.py` — `ModuleServiceManifest`, `ModuleRemoteManifest`, parsing.
- `minder/core/context_engineering/tools/registry.py` — merge remote proxy tools into skill specs.
- `minder/core/context_engineering/tools/protected_paths.py` — protect `backend/sample_manuals`.
- `minder/web/routes/modules.py` — surface `remote`/`remote_entry` in the dashboards listing.
- `docker-compose.yml` — add the `maintenance-copilot` service.
- `web-ui/package.json`, `web-ui/vite.config.ts` — federation host wiring.
- `web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx` — `remote` render branch.
- `web-ui/src/stores/modules.ts`, `web-ui/src/types/index.ts`, `web-ui/src/api/modules.ts` — carry remote fields.

---

# Phase 1 — Backend extraction

Goal: a standalone container that answers `maintenance_copilot_query` over HTTP and produces the exact structured card. Verifiable independently via `curl`.

### Task 1.1: Move the pipeline and corpus into `backend/`

**Files:**
- Create dir: `modules/maintenance_copilot/backend/pipeline/` (moved `scripts/*.py`)
- Create dir: `modules/maintenance_copilot/backend/sample_manuals/` (moved corpus)
- Create: `modules/maintenance_copilot/backend/requirements.txt`

**Interfaces:**
- Produces: `backend/pipeline/copilot.py` exposing `_build_store()`, `synthesize_answer(text, hits)`, `build_parser()`, `main(argv)` (unchanged from today); `backend/pipeline/{guardrails,answer_schema,audit,conn_errors,index_store,...}.py`.

- [ ] **Step 1: Move scripts and corpus (git mv preserves history)**

```bash
cd /Users/anlnm/Desktop/Project/opendev-py
mkdir -p modules/maintenance_copilot/backend
git mv modules/maintenance_copilot/scripts modules/maintenance_copilot/backend/pipeline
git mv modules/maintenance_copilot/sample_manuals modules/maintenance_copilot/backend/sample_manuals
```

- [ ] **Step 2: Create the service requirements file**

Create `modules/maintenance_copilot/backend/requirements.txt`:

```
fastapi>=0.111
uvicorn[standard]>=0.30
httpx>=0.27
pydantic>=2.7
openai>=1.40
qdrant-client>=1.11
neo4j>=5.24
chonkie>=1.0
```

- [ ] **Step 3: Verify the pipeline still imports from its new home**

Run:
```bash
cd modules/maintenance_copilot/backend/pipeline && python -c "import sys; sys.path.insert(0, '.'); import copilot; print('ok', hasattr(copilot, 'synthesize_answer'))"
```
Expected: `ok True` (the flat-dir `sys.path` import trick copilot uses still works because the files moved together).

- [ ] **Step 4: Commit**

```bash
cd /Users/anlnm/Desktop/Project/opendev-py
git add -A modules/maintenance_copilot/backend
git commit -m "refactor(maintenance_copilot): move pipeline + corpus into backend/"
```

---

### Task 1.2: Extract `service.py` — pipeline entry without the Minder import

**Files:**
- Create: `modules/maintenance_copilot/backend/service.py`
- Test: `tests/test_connector_app.py` (created here, expanded in 1.3)

**Interfaces:**
- Consumes: `backend/pipeline/{copilot,guardrails,answer_schema,audit,conn_errors}.py`.
- Produces:
  - `class ServiceUnavailableError(RuntimeError)` with `.service: str`.
  - `run_query(query: str, k: int = 5, ata: str | None = None, revision: str = "current") -> dict` — returns the full card dict (keys: `query, answer, answer_type, exact_quote, is_sensitive, related_suggestions, data_collection_requirement, citations, confidence, confidence_band, review_required, advisory_note, validation_warnings, structured`). Raises `ServiceUnavailableError` when a sidecar is down.
  - `unavailable_payload(query: str, service: str) -> dict` — same-shaped card for a down sidecar.
  - `UNAVAILABLE_SUFFIX: str` — the `_llm_suffix` template with a `{service}` field.

- [ ] **Step 1: Write the failing test**

Create `tests/test_connector_app.py`:

```python
"""Contract tests for the maintenance_copilot connector service.

These import the service module directly (not over HTTP) with the pipeline
mocked, so they run without qdrant/llm sidecars.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "modules/maintenance_copilot/backend"


def _load_service():
    """Import backend/service.py with its pipeline dir on sys.path."""
    sys.path.insert(0, str(BACKEND / "pipeline"))
    spec = importlib.util.spec_from_file_location("mc_service", BACKEND / "service.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unavailable_payload_is_low_confidence_review_required():
    svc = _load_service()
    card = svc.unavailable_payload("why is the APU inop?", "qdrant")
    assert card["confidence"] == 0.0
    assert card["confidence_band"] == "low"
    assert card["review_required"] is True
    assert card["citations"] == []
    assert card["validation_warnings"] == ["service_unavailable:qdrant"]


def test_unavailable_suffix_names_service():
    svc = _load_service()
    assert "{service}" in svc.UNAVAILABLE_SUFFIX
    assert "Do NOT" in svc.UNAVAILABLE_SUFFIX
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_connector_app.py -v`
Expected: FAIL — `service.py` does not exist yet (import error).

- [ ] **Step 3: Create `service.py`**

Create `modules/maintenance_copilot/backend/service.py` by copying the brains of the current `tools.py` and dropping the Minder coupling. Full content:

```python
"""Pure pipeline entry for the maintenance_copilot connector service.

This is the intelligence that used to live in the module's in-process
``tools.py`` — retrieval + synthesis + citation/confidence guardrails — with
the Minder ``ToolSpec`` coupling removed. The connector ``app.py`` calls
``run_query`` and shapes the HTTP response; nothing here imports ``minder``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# pipeline/ is a flat, non-package dir; putting it on sys.path lets copilot run
# its own sys.path.insert so budget/guardrails/synthesis/index_store/audit
# resolve as bare imports (identical to the old scripts/ layout).
_PIPELINE = Path(__file__).resolve().parent / "pipeline"
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import answer_schema  # noqa: E402
import audit  # noqa: E402
import conn_errors  # noqa: E402
import copilot  # noqa: E402
import guardrails  # noqa: E402

_MEDIUM_FLOOR = 0.6


class ServiceUnavailableError(RuntimeError):
    """A copilot sidecar (retrieval or LLM) is unreachable."""

    def __init__(self, service: str) -> None:
        super().__init__(f"maintenance copilot service unavailable: {service}")
        self.service = service


_UNAVAILABLE_ANSWER = (
    "The maintenance copilot's {label} is currently unavailable ({service} sidecar "
    "unreachable), so this question cannot be answered with grounded citations "
    "right now. Please retry once the service is restored; an operator can run "
    "`python copilot.py health` to diagnose."
)

_SERVICE_LABELS = {"qdrant": "retrieval service", "llm": "synthesis model"}

UNAVAILABLE_SUFFIX = (
    "\n\n[SYSTEM: The maintenance copilot service is unavailable ({service}). "
    "Tell the user the copilot cannot answer right now and that the structured "
    "card above explains why. Do NOT read the manual files in sample_manuals, "
    "do NOT grep or cat them via bash, and do NOT answer the maintenance "
    "question from your own knowledge.]"
)


def unavailable_payload(query: str, service: str) -> dict:
    """Structured service-unavailable card (strict-schema JSON, low confidence)."""
    label = _SERVICE_LABELS.get(service, "service")
    structured = answer_schema.CopilotAnswer(
        answer_type="clarification_needed",
        response=answer_schema.ResponseBlock(
            primary_answer=_UNAVAILABLE_ANSWER.format(label=label, service=service),
            exact_quote="",
            is_sensitive=False,
        ),
        citations=[],
        related_suggestions=[],
        data_collection_requirement=answer_schema.DataCollectionRequirement(
            needs_user_input=False, missing_fields=[]
        ),
    ).model_dump()
    result = {
        "query": query,
        "answer": structured["response"]["primary_answer"],
        "answer_type": "clarification_needed",
        "exact_quote": "",
        "is_sensitive": False,
        "related_suggestions": [],
        "data_collection_requirement": structured["data_collection_requirement"],
        "citations": [],
        "confidence": 0.0,
        "confidence_band": "low",
        "review_required": True,
        "advisory_note": guardrails.ADVISORY_NOTE,
        "validation_warnings": [f"service_unavailable:{service}"],
        "structured": structured,
    }
    try:
        audit.append_event({"type": "query", "query": query, "citations": [],
                            "needs_review": True, "answer_type": "clarification_needed",
                            "validation_warnings": result["validation_warnings"],
                            "attempts": 0, "json_mode": ""})
    except Exception:
        pass
    return result


def run_query(query: str, k: int = 5, ata: str | None = None,
              revision: str = "current") -> dict:
    """Grounded maintenance query → structured card dict. Raises on sidecar down."""
    rev = None if str(revision).lower() == "none" else revision
    try:
        store = copilot._build_store()
        hits = store.query(query, k=k, ata_chapter=ata, revision=rev)
    except Exception as exc:
        if conn_errors.is_connectivity(exc):
            raise ServiceUnavailableError("qdrant") from exc
        raise
    try:
        ans = copilot.synthesize_answer(query, hits)
    except Exception as exc:
        if conn_errors.is_connectivity(exc):
            raise ServiceUnavailableError("llm") from exc
        raise
    structured = ans["structured"]
    response = structured["response"]

    by_id = {h.get("chunk_id"): h for h in hits}
    citations = []
    for cit in structured["citations"]:
        h = by_id.get(cit["chunk_id"], {})
        citations.append({
            "chunk_id": cit["chunk_id"],
            "doc": h.get("doc_type", ""),
            "revision": h.get("revision", ""),
            "ata": h.get("ata_chapter", ""),
            "citation": h.get("citation", cit["chunk_id"]),
            "source_id": cit["source_id"],
            "source_name": cit["source_name"],
            "source_path": cit["source_path"],
            "page_number": cit["page_number"],
            "confidence_score": round(cit["confidence_score"], 3),
            "char_start": cit["char_start"],
            "char_end": cit["char_end"],
        })

    confidence = float(ans.get("confidence", 0.0))
    review_required = structured["answer_type"] == "clarification_needed"
    floor = guardrails.default_min_confidence()
    if review_required or confidence < floor:
        band = "low"
    elif confidence < _MEDIUM_FLOOR:
        band = "medium"
    else:
        band = "high"

    result = {
        "query": query,
        "answer": response["primary_answer"],
        "answer_type": structured["answer_type"],
        "exact_quote": response["exact_quote"],
        "is_sensitive": response["is_sensitive"],
        "related_suggestions": structured["related_suggestions"],
        "data_collection_requirement": structured["data_collection_requirement"],
        "citations": citations,
        "confidence": round(confidence, 3),
        "confidence_band": band,
        "review_required": review_required,
        "advisory_note": ans.get("disclaimer", ""),
        "validation_warnings": ans.get("validation_warnings", []),
        "structured": structured,
    }
    try:
        audit.append_event({"type": "query", "query": query,
                            "citations": [c["chunk_id"] for c in citations],
                            "needs_review": review_required,
                            "answer_type": structured["answer_type"],
                            "validation_warnings": result["validation_warnings"],
                            "attempts": ans.get("attempts", 0),
                            "json_mode": ans.get("json_mode", "")})
    except Exception:
        pass
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/test_connector_app.py -v`
Expected: PASS (both tests). `unavailable_payload` needs no live sidecar.

- [ ] **Step 5: Commit**

```bash
git add modules/maintenance_copilot/backend/service.py tests/test_connector_app.py
git commit -m "feat(maintenance_copilot): extract service.py pipeline entry (no minder import)"
```

---

### Task 1.3: Implement the FastAPI connector contract (`app.py`)

**Files:**
- Create: `modules/maintenance_copilot/backend/app.py`
- Test: `tests/test_connector_app.py` (expand)

**Interfaces:**
- Consumes: `service.run_query`, `service.unavailable_payload`, `service.UNAVAILABLE_SUFFIX`, `service.ServiceUnavailableError`.
- Produces (HTTP contract):
  - `GET /connector/health` → `{"ok": true, "module": "maintenance_copilot", "version": "1"}`
  - `GET /connector/manifest` → `{"name","display_name","tools":[...],"remote":{...},"version"}`
  - `POST /connector/tools/{name}` body `{"arguments": {...}}` → `{"success": bool, "output": <card|error>, "card": <card>|null, "llm_suffix": <str>|null}`
  - `POST /connector/run` body `{"action": str, "args": {...}}` → result dict

- [ ] **Step 1: Write the failing test (with the pipeline mocked)**

Append to `tests/test_connector_app.py`:

```python
def _client(monkeypatch, run_query_impl):
    """Build a TestClient with service.run_query patched."""
    from fastapi.testclient import TestClient

    sys.path.insert(0, str(BACKEND / "pipeline"))
    spec = importlib.util.spec_from_file_location("mc_app", BACKEND / "app.py")
    app_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_mod)
    monkeypatch.setattr(app_mod.service, "run_query", run_query_impl)
    return TestClient(app_mod.app), app_mod


def test_health_ok(monkeypatch):
    client, _ = _client(monkeypatch, lambda **k: {})
    r = client.get("/connector/health")
    assert r.status_code == 200
    assert r.json()["module"] == "maintenance_copilot"


def test_manifest_lists_the_query_tool(monkeypatch):
    client, _ = _client(monkeypatch, lambda **k: {})
    body = client.get("/connector/manifest").json()
    names = [t["name"] for t in body["tools"]]
    assert "maintenance_copilot_query" in names
    assert body["remote"]["exposed"]["dashboard"] == "./Dashboard"


def test_tool_call_returns_card(monkeypatch):
    fake = {"answer": "Torque to 40 Nm.", "confidence": 0.9, "confidence_band": "high",
            "citations": [], "review_required": False}
    client, _ = _client(monkeypatch, lambda **k: fake)
    r = client.post("/connector/tools/maintenance_copilot_query",
                    json={"arguments": {"query": "torque?"}})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["card"]["answer"] == "Torque to 40 Nm."
    assert body["llm_suffix"] is None


def test_tool_call_sidecar_down_returns_unavailable_card_and_suffix(monkeypatch):
    from importlib import import_module  # noqa: F401

    def boom(**k):
        raise app_unavailable_error("qdrant")

    # Resolve ServiceUnavailableError from the loaded service module.
    sys.path.insert(0, str(BACKEND / "pipeline"))
    svc_spec = importlib.util.spec_from_file_location("mc_service2", BACKEND / "service.py")
    svc = importlib.util.module_from_spec(svc_spec)
    svc_spec.loader.exec_module(svc)
    globals()["app_unavailable_error"] = svc.ServiceUnavailableError

    client, _ = _client(monkeypatch, boom)
    r = client.post("/connector/tools/maintenance_copilot_query",
                    json={"arguments": {"query": "torque?"}})
    body = r.json()
    assert body["success"] is True  # fail-closed but structured, not an error
    assert body["card"]["review_required"] is True
    assert "qdrant" in body["llm_suffix"]


def test_unknown_tool_is_404(monkeypatch):
    client, _ = _client(monkeypatch, lambda **k: {})
    r = client.post("/connector/tools/nope", json={"arguments": {}})
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_connector_app.py -v`
Expected: FAIL — `app.py` does not exist.

- [ ] **Step 3: Create `app.py`**

Create `modules/maintenance_copilot/backend/app.py`:

```python
"""maintenance_copilot connector service — the HTTP contract Minder speaks.

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --no-sync pytest tests/test_connector_app.py -v`
Expected: PASS (all tests). The pipeline is mocked, so no sidecars needed.

- [ ] **Step 5: Commit**

```bash
git add modules/maintenance_copilot/backend/app.py tests/test_connector_app.py
git commit -m "feat(maintenance_copilot): FastAPI connector contract (health/manifest/tools/run)"
```

---

### Task 1.4: Containerize + compose entry + retire the in-process surface

**Files:**
- Create: `modules/maintenance_copilot/backend/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `modules/maintenance_copilot/SKILL.md` (drop `tools:`)
- Delete: `modules/maintenance_copilot/tools.py`, `modules/maintenance_copilot/requirements.txt`, `modules/maintenance_copilot/.deps.sha256`

**Interfaces:**
- Produces: a running container `maintenance-copilot` reachable at `http://maintenance-copilot:9200` (in-network) / `http://localhost:9200` (host).

- [ ] **Step 1: Create the Dockerfile**

Create `modules/maintenance_copilot/backend/Dockerfile`:

```dockerfile
# Standalone maintenance_copilot RAG service. Kept OUT of the main minder image:
# openai/qdrant-client/neo4j/chonkie + the pipeline only run here.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# pipeline/, sample_manuals/, service.py, app.py
COPY . /app

ENV PYTHONUNBUFFERED=1 \
    MC_PUBLIC_BASE=http://localhost:9200

EXPOSE 9200

# service.py puts pipeline/ on sys.path at import; run from /app so `import service`
# and `import app` resolve.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9200"]
```

- [ ] **Step 2: Add the compose service**

In `docker-compose.yml`, add under `services:` (mirror the `asr` block; wire the sidecar env the pipeline reads — reuse the existing `qdrant`/`tei`/`neo4j`/`copilot-llm` services):

```yaml
  maintenance-copilot:
    build: ./modules/maintenance_copilot/backend
    ports:
      - "9200:9200"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - QDRANT_URL=http://qdrant:6333
      - NEO4J_URI=bolt://neo4j:7687
      - MC_PUBLIC_BASE=http://localhost:9200
    depends_on:
      - qdrant
      - neo4j
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:9200/connector/health')"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 30s
    restart: unless-stopped
```

> NOTE for implementer: confirm the exact env var names the pipeline reads by grepping `modules/maintenance_copilot/backend/pipeline/config.py` for `os.environ`. Match them here; the names above are the conventional ones and may need adjusting.

- [ ] **Step 3: Drop the in-process tool from the Minder surface**

Delete the files Minder no longer loads:

```bash
git rm modules/maintenance_copilot/tools.py modules/maintenance_copilot/requirements.txt modules/maintenance_copilot/.deps.sha256
```

Then edit `modules/maintenance_copilot/SKILL.md`: remove the `tools: tools.py` line from its YAML frontmatter (so `SkillToolLoader` no longer tries to load it). Leave the rest of SKILL.md intact.

- [ ] **Step 4: Verify Minder no longer imports the heavy deps for this module**

Run:
```bash
grep -rn "tools:" modules/maintenance_copilot/SKILL.md || echo "no tools: line — good"
uv run --no-sync pytest tests/ -k "module or registry or skill_tool" -q
```
Expected: the `tools:` line is gone; existing module/registry tests still pass (the module now has no in-process tools).

- [ ] **Step 5: Build the service image**

Run:
```bash
docker compose build maintenance-copilot
```
Expected: image builds; heavy deps install inside the image, not in Minder's.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(maintenance_copilot): containerize service + compose entry; retire in-process tool"
```

---

# Phase 2 — Minder consumer (remote registry + proxy tool)

Goal: Minder registers `maintenance_copilot_query` as an HTTP proxy from the committed manifest, re-broadcasts the card, and fails closed when the connector is down. After this phase the dep-isolation win is fully live end-to-end (dashboard still iframe).

### Task 2.1: Manifest schema — `service` + `remote` blocks

**Files:**
- Modify: `minder/core/modules/store.py`
- Test: `tests/test_module_service_manifest.py`

**Interfaces:**
- Produces (on `ModuleManifest`):
  - `service: ModuleServiceManifest | None` where `ModuleServiceManifest = {connector_url: str, health_path: str = "/connector/health", tools: list[dict]}`.
  - `remote: ModuleRemoteManifest | None` where `ModuleRemoteManifest = {name: str, remote_entry: str, exposed: dict}`.
- Consumed by: Task 2.3 (`build_remote_tool_specs`), Task 4.4 (routes surface `remote`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_module_service_manifest.py`:

```python
"""Manifest parsing for service-module `service`/`remote` blocks."""
from __future__ import annotations

import json
from pathlib import Path

from minder.core.modules import store


def _write_module(tmp_path: Path) -> Path:
    d = tmp_path / "svcmod"
    d.mkdir()
    (d / "SKILL.md").write_text("---\ndescription: test\n---\nbody\n")
    (d / "manifest.json").write_text(json.dumps({
        "display_name": "Svc Mod",
        "service": {
            "connector_url": "http://svcmod:9200",
            "tools": [{"name": "svc_query", "description": "q", "parameters": {"type": "object"}}],
        },
        "remote": {
            "name": "svcmod",
            "remoteEntry": "http://localhost:9200/dashboard/remoteEntry.js",
            "exposed": {"dashboard": "./Dashboard"},
        },
    }))
    return d


def test_service_and_remote_blocks_parse(tmp_path):
    _write_module(tmp_path)
    m = store.read_module(tmp_path, "svcmod")
    assert m.manifest.service is not None
    assert m.manifest.service.connector_url == "http://svcmod:9200"
    assert m.manifest.service.health_path == "/connector/health"  # default
    assert m.manifest.service.tools[0]["name"] == "svc_query"
    assert m.manifest.remote.remote_entry == "http://localhost:9200/dashboard/remoteEntry.js"
    assert m.manifest.remote.exposed["dashboard"] == "./Dashboard"


def test_module_without_service_block_is_none(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    (d / "SKILL.md").write_text("---\ndescription: t\n---\nx\n")
    (d / "manifest.json").write_text(json.dumps({"display_name": "Plain"}))
    m = store.read_module(tmp_path, "plain")
    assert m.manifest.service is None
    assert m.manifest.remote is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_module_service_manifest.py -v`
Expected: FAIL — `ModuleManifest` has no `service`/`remote` attributes.

- [ ] **Step 3: Add the dataclasses + parsing**

In `minder/core/modules/store.py`, after `ModuleSubagentManifest`, add:

```python
@dataclass
class ModuleServiceManifest:
    """Declares that a module runs as an out-of-process connector service."""

    connector_url: str
    tools: List[Dict[str, Any]] = field(default_factory=list)
    health_path: str = "/connector/health"


@dataclass
class ModuleRemoteManifest:
    """Declares a module's Module-Federation frontend remote."""

    name: str
    remote_entry: str
    exposed: Dict[str, Any] = field(default_factory=dict)
```

Add the two fields to `ModuleManifest`:

```python
    subagent: Optional[ModuleSubagentManifest] = None
    service: Optional["ModuleServiceManifest"] = None
    remote: Optional["ModuleRemoteManifest"] = None
```

Then in the manifest-parsing function (find where `ModuleManifest(...)` is constructed from parsed JSON — search `def _parse_manifest` / `ModuleManifest(`), parse the blocks before constructing:

```python
    service_raw = data.get("service")
    service = None
    if isinstance(service_raw, dict) and service_raw.get("connector_url"):
        service = ModuleServiceManifest(
            connector_url=str(service_raw["connector_url"]),
            tools=list(service_raw.get("tools") or []),
            health_path=str(service_raw.get("health_path", "/connector/health")),
        )

    remote_raw = data.get("remote")
    remote = None
    if isinstance(remote_raw, dict) and remote_raw.get("remoteEntry"):
        remote = ModuleRemoteManifest(
            name=str(remote_raw.get("name", "")),
            remote_entry=str(remote_raw["remoteEntry"]),
            exposed=dict(remote_raw.get("exposed") or {}),
        )
```

and pass `service=service, remote=remote` into the `ModuleManifest(...)` call. (Ensure `Any` is imported — it already is in the `typing` import line.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/test_module_service_manifest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add minder/core/modules/store.py tests/test_module_service_manifest.py
git commit -m "feat(modules): parse service/remote manifest blocks"
```

---

### Task 2.2: `RemoteConnector` HTTP client

**Files:**
- Create: `minder/core/modules/remote.py`
- Test: `tests/test_remote_connector.py`

**Interfaces:**
- Produces:
  - `class RemoteConnector` with `__init__(self, name: str, connector_url: str, health_path: str = "/connector/health")`.
  - `.is_healthy(self, timeout: float = 2.0) -> bool`.
  - `.call_tool(self, tool: str, arguments: dict, timeout: float = 110.0) -> dict` — returns the connector's `{success, output, card, llm_suffix}` dict; raises `ConnectorUnreachable` on network failure.
  - `class ConnectorUnreachable(RuntimeError)` with `.service = "connector"`.
  - `unavailable_card(query: str, connector_name: str) -> dict` — plain-dict (no pydantic) fail-closed card matching the maintenance card shape, used when the connector itself is down.
  - `UNAVAILABLE_SUFFIX: str` — the connector-down `_llm_suffix` (same directive as the service's).

- [ ] **Step 1: Write the failing test**

Create `tests/test_remote_connector.py`:

```python
"""Unit tests for the Minder-side remote connector client (httpx mocked)."""
from __future__ import annotations

import httpx
import pytest

from minder.core.modules import remote


def _connector(handler):
    transport = httpx.MockTransport(handler)
    conn = remote.RemoteConnector("maintenance_copilot", "http://mc:9200")
    conn._client = httpx.Client(transport=transport, base_url="http://mc:9200")
    return conn


def test_call_tool_returns_connector_payload():
    def handler(request):
        assert request.url.path == "/connector/tools/maintenance_copilot_query"
        return httpx.Response(200, json={"success": True, "output": {"answer": "42"},
                                         "card": {"answer": "42"}, "llm_suffix": None})
    conn = _connector(handler)
    out = conn.call_tool("maintenance_copilot_query", {"query": "q"})
    assert out["card"]["answer"] == "42"


def test_call_tool_network_error_raises_unreachable():
    def handler(request):
        raise httpx.ConnectError("refused")
    conn = _connector(handler)
    with pytest.raises(remote.ConnectorUnreachable):
        conn.call_tool("maintenance_copilot_query", {"query": "q"})


def test_is_healthy_true_on_200():
    def handler(request):
        assert request.url.path == "/connector/health"
        return httpx.Response(200, json={"ok": True})
    assert _connector(handler).is_healthy() is True


def test_is_healthy_false_on_error():
    def handler(request):
        raise httpx.ConnectError("refused")
    assert _connector(handler).is_healthy() is False


def test_unavailable_card_is_fail_closed_plain_dict():
    card = remote.unavailable_card("q", "maintenance_copilot")
    assert card["review_required"] is True
    assert card["confidence"] == 0.0
    assert card["confidence_band"] == "low"
    assert card["citations"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_remote_connector.py -v`
Expected: FAIL — `minder/core/modules/remote.py` does not exist.

- [ ] **Step 3: Create `remote.py`**

Create `minder/core/modules/remote.py`:

```python
"""Minder-side client for a module's out-of-process connector service.

Registration is deterministic from the committed manifest (Task 2.3); this
client is only touched at *call time*. A dead connector fails closed with a
structured card, never a crash and never freelancing over the corpus.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class ConnectorUnreachable(RuntimeError):
    """The connector service could not be reached over the network."""

    service = "connector"


# Connector-down directive for the model (mirrors the service's UNAVAILABLE_SUFFIX
# but built on the Minder side, deps-free, when the whole container is down).
UNAVAILABLE_SUFFIX = (
    "\n\n[SYSTEM: The maintenance copilot service is unavailable (connector "
    "unreachable). Tell the user the copilot cannot answer right now and that the "
    "structured card above explains why. Do NOT read the manual files in "
    "sample_manuals, do NOT grep or cat them via bash, and do NOT answer the "
    "maintenance question from your own knowledge.]"
)

_UNAVAILABLE_ANSWER = (
    "The maintenance copilot service is currently unavailable (connector "
    "unreachable), so this question cannot be answered with grounded citations "
    "right now. Please retry once the service is restored."
)


def unavailable_card(query: str, connector_name: str) -> dict:
    """A deps-free, fail-closed card matching the maintenance-answer shape."""
    return {
        "query": query,
        "answer": _UNAVAILABLE_ANSWER,
        "answer_type": "clarification_needed",
        "exact_quote": "",
        "is_sensitive": False,
        "related_suggestions": [],
        "data_collection_requirement": {"needs_user_input": False, "missing_fields": []},
        "citations": [],
        "confidence": 0.0,
        "confidence_band": "low",
        "review_required": True,
        "advisory_note": "",
        "validation_warnings": [f"connector_unreachable:{connector_name}"],
        "structured": {},
    }


class RemoteConnector:
    """Thin HTTP client for one module's connector service."""

    def __init__(self, name: str, connector_url: str,
                 health_path: str = "/connector/health") -> None:
        self.name = name
        self.base_url = connector_url.rstrip("/")
        self.health_path = health_path
        self._client = httpx.Client(base_url=self.base_url)

    def is_healthy(self, timeout: float = 2.0) -> bool:
        try:
            r = self._client.get(self.health_path, timeout=timeout)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def call_tool(self, tool: str, arguments: dict, timeout: float = 110.0) -> dict:
        try:
            r = self._client.post(f"/connector/tools/{tool}",
                                  json={"arguments": arguments}, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.warning("connector %s call_tool(%s) failed: %s", self.name, tool, exc)
            raise ConnectorUnreachable(str(exc)) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/test_remote_connector.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add minder/core/modules/remote.py tests/test_remote_connector.py
git commit -m "feat(modules): RemoteConnector HTTP client + fail-closed card"
```

---

### Task 2.3: `build_remote_tool_specs` — proxy `ToolSpec`s that re-broadcast the card

**Files:**
- Modify: `minder/core/modules/remote.py`
- Test: `tests/test_remote_connector.py` (expand)

**Interfaces:**
- Consumes: `store.Module` (with `manifest.service`), `RemoteConnector`, `SkillToolContext`, `ToolSpec`.
- Produces: `build_remote_tool_specs(ctx: SkillToolContext, modules: list[Module]) -> list[ToolSpec]`. For each module with a `service` manifest, one `ToolSpec` per declared tool whose handler: calls the connector; on success returns `{"success": True, "output": <output>}` and broadcasts `{"type": "maintenance_answer", **card}` if a `card` is present; on `ConnectorUnreachable` returns the fail-closed card + sets `_llm_suffix`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_remote_connector.py`:

```python
from dataclasses import dataclass, field as _field


@dataclass
class _FakeManifestService:
    connector_url: str
    tools: list = _field(default_factory=list)
    health_path: str = "/connector/health"


@dataclass
class _FakeManifest:
    service: object = None


@dataclass
class _FakeModule:
    name: str
    manifest: object


def _module_with_tool():
    svc = _FakeManifestService(
        connector_url="http://mc:9200",
        tools=[{"name": "maintenance_copilot_query", "description": "q",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                               "required": ["query"]}}],
    )
    return _FakeModule("maintenance_copilot", _FakeManifest(service=svc))


def test_build_specs_registers_declared_tools(monkeypatch):
    from minder.core.skill_tools import SkillToolContext

    broadcasts = []
    ctx = SkillToolContext(broadcaster=broadcasts.append)

    def fake_call(self, tool, arguments, timeout=110.0):
        return {"success": True, "output": {"answer": "ok"},
                "card": {"answer": "ok", "review_required": False}, "llm_suffix": None}
    monkeypatch.setattr(remote.RemoteConnector, "call_tool", fake_call)

    specs = remote.build_remote_tool_specs(ctx, [_module_with_tool()])
    assert [s.name for s in specs] == ["maintenance_copilot_query"]

    out = specs[0].handler(query="torque?")
    assert out["success"] is True
    assert out["output"]["answer"] == "ok"
    assert broadcasts == [{"type": "maintenance_answer", "answer": "ok", "review_required": False}]


def test_handler_connector_down_fails_closed(monkeypatch):
    from minder.core.skill_tools import SkillToolContext

    broadcasts = []
    ctx = SkillToolContext(broadcaster=broadcasts.append)

    def boom(self, tool, arguments, timeout=110.0):
        raise remote.ConnectorUnreachable("refused")
    monkeypatch.setattr(remote.RemoteConnector, "call_tool", boom)

    specs = remote.build_remote_tool_specs(ctx, [_module_with_tool()])
    out = specs[0].handler(query="torque?")
    assert out["success"] is True
    assert out["output"]["review_required"] is True
    assert "connector unreachable" in out["_llm_suffix"].lower()
    assert broadcasts[0]["type"] == "maintenance_answer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_remote_connector.py -v`
Expected: FAIL — `build_remote_tool_specs` undefined.

- [ ] **Step 3: Add `build_remote_tool_specs`**

Append to `minder/core/modules/remote.py`:

```python
from typing import TYPE_CHECKING, Any, Callable  # noqa: E402

if TYPE_CHECKING:  # avoid import cycles / heavy imports at module load
    from minder.core.modules.store import Module
    from minder.core.skill_tools import SkillToolContext, ToolSpec


def _make_handler(ctx: "SkillToolContext", conn: "RemoteConnector",
                  tool_name: str) -> Callable[..., dict]:
    def handler(**kwargs: Any) -> dict:
        query = str(kwargs.get("query") or kwargs.get("text") or "")
        try:
            resp = conn.call_tool(tool_name, kwargs)
        except ConnectorUnreachable:
            card = unavailable_card(query, conn.name)
            if ctx.broadcaster:
                try:
                    ctx.broadcaster({"type": "maintenance_answer", **card})
                except Exception as exc:  # noqa: BLE001
                    ctx.logger.warning("card broadcast failed: %s", exc)
            return {"success": True, "output": card, "_llm_suffix": UNAVAILABLE_SUFFIX}

        card = resp.get("card")
        if card and ctx.broadcaster:
            try:
                ctx.broadcaster({"type": "maintenance_answer", **card})
            except Exception as exc:  # noqa: BLE001
                ctx.logger.warning("card broadcast failed: %s", exc)
        out: dict = {"success": bool(resp.get("success", True)), "output": resp.get("output")}
        if resp.get("llm_suffix"):
            out["_llm_suffix"] = resp["llm_suffix"]
        return out

    return handler


def build_remote_tool_specs(ctx: "SkillToolContext",
                            modules: "list[Module]") -> "list[ToolSpec]":
    """Build proxy ToolSpecs for every service-module, from its committed manifest."""
    from minder.core.skill_tools import ToolSpec  # local import: avoid cycle at module load

    specs: list[ToolSpec] = []
    for module in modules:
        svc = getattr(module.manifest, "service", None) if module.manifest else None
        if not svc:
            continue
        conn = RemoteConnector(module.name, svc.connector_url, svc.health_path)
        for tool in svc.tools:
            name = tool.get("name")
            if not name:
                continue
            specs.append(ToolSpec(
                name=name,
                description=tool.get("description", ""),
                parameters=tool.get("parameters", {"type": "object", "properties": {}}),
                handler=_make_handler(ctx, conn, name),
            ))
    return specs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/test_remote_connector.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add minder/core/modules/remote.py tests/test_remote_connector.py
git commit -m "feat(modules): build_remote_tool_specs — proxy tools that re-broadcast the card"
```

---

### Task 2.4: Wire remote proxy tools into the tool registry + protect the corpus

**Files:**
- Modify: `minder/core/context_engineering/tools/registry.py`
- Modify: `minder/core/context_engineering/tools/protected_paths.py`
- Test: `tests/test_remote_registry_wiring.py`

**Interfaces:**
- Consumes: `remote.build_remote_tool_specs`, `get_registry()` (module registry), the existing `self._skill_specs` dict.
- Produces: after registry init, `self._skill_specs` contains the remote proxy tools (merged; remote specs win on name collision, since the in-process `tools.py` is gone).

- [ ] **Step 1: Write the failing test**

Create `tests/test_remote_registry_wiring.py`:

```python
"""The tool registry merges remote proxy tools from service-modules."""
from __future__ import annotations

from minder.core.skill_tools import SkillToolContext, ToolSpec


def test_merge_remote_specs_into_skill_specs():
    # Emulate the merge the registry performs (unit-level; no full registry boot).
    from minder.core.modules import remote

    ctx = SkillToolContext()

    class _Svc:
        connector_url = "http://mc:9200"
        health_path = "/connector/health"
        tools = [{"name": "maintenance_copilot_query", "description": "q",
                  "parameters": {"type": "object"}}]

    class _Manifest:
        service = _Svc()

    class _Mod:
        name = "maintenance_copilot"
        manifest = _Manifest()

    specs = remote.build_remote_tool_specs(ctx, [_Mod()])
    skill_specs: dict[str, ToolSpec] = {}
    for s in specs:
        skill_specs[s.name] = s
    assert "maintenance_copilot_query" in skill_specs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_remote_registry_wiring.py -v`
Expected: PASS-or-FAIL — this test only exercises `build_remote_tool_specs` (already implemented), so it should PASS. Its purpose is a regression guard for the merge contract. If it fails, `build_remote_tool_specs` regressed.

- [ ] **Step 3: Merge remote specs in the registry**

In `minder/core/context_engineering/tools/registry.py`, immediately after the block that builds `self._skill_specs` (the `try/except` around `SkillToolLoader(...).discover_and_register(...)`, ~line 116-123), add:

```python
        # Merge remote proxy tools from service-modules (out-of-process connectors).
        # These replace what an in-process tools.py used to provide; on name
        # collision the remote spec wins (the local tools.py has been retired).
        try:
            from minder.core.modules.registry import get_registry as _get_mod_registry
            from minder.core.modules.remote import build_remote_tool_specs

            _remote_specs = build_remote_tool_specs(self.skill_ctx, _get_mod_registry().all())
            for _spec in _remote_specs:
                self._skill_specs[_spec.name] = _spec
            if _remote_specs:
                logger.info("registered %d remote proxy tool(s)", len(_remote_specs))
        except Exception as exc:  # noqa: BLE001 — never block registry init
            logger.warning("remote proxy tool registration failed: %s", exc)
```

- [ ] **Step 4: Protect the relocated corpus**

In `minder/core/context_engineering/tools/protected_paths.py`, find the default protected globs (search `sample_manuals`). Update/confirm the default protects the new location. If the default is a glob like `modules/*/sample_manuals`, add `modules/*/backend/sample_manuals`:

```python
    # (in the DEFAULT protected-path list)
    "modules/*/sample_manuals",
    "modules/*/backend/sample_manuals",  # corpus moved under backend/ (service-module)
```

- [ ] **Step 5: Run the tests**

Run:
```bash
uv run --no-sync pytest tests/test_remote_registry_wiring.py tests/test_remote_connector.py -v
uv run --no-sync pytest tests/ -k "protected or registry" -q
```
Expected: PASS. Protected-path tests still pass with the added glob.

- [ ] **Step 6: Commit**

```bash
git add minder/core/context_engineering/tools/registry.py minder/core/context_engineering/tools/protected_paths.py tests/test_remote_registry_wiring.py
git commit -m "feat(tools): register remote proxy tools; protect relocated corpus"
```

---

### Task 2.5: Phase-2 end-to-end verification (real API, per project rules)

**Files:** none (verification only).

- [ ] **Step 1: Bring up the stack**

```bash
export OPENAI_API_KEY="<real key>"
docker compose up -d qdrant neo4j maintenance-copilot
docker compose ps   # maintenance-copilot healthy
```

- [ ] **Step 2: Ingest the corpus into the running service**

```bash
docker compose exec maintenance-copilot python pipeline/copilot.py ingest
```
Expected: index built (the service owns the pipeline now).

- [ ] **Step 3: Hit the connector directly**

```bash
curl -s localhost:9200/connector/health
curl -s -X POST localhost:9200/connector/tools/maintenance_copilot_query \
  -H 'content-type: application/json' \
  -d '{"arguments":{"query":"What is the MEL dispatch condition for an inop APU?"}}' | python -m json.tool
```
Expected: `success: true`, a `card` with grounded `citations` and a `confidence_band`.

- [ ] **Step 4: Verify through Minder's proxy tool + guardrail**

Run Minder (web or `-p`) with the same env, ask a maintenance question, and confirm: the `maintenance_copilot_query` tool fires, the `maintenance_answer` card renders in the UI, and the agent does NOT read `sample_manuals` (guardrail intact). Then stop the service (`docker compose stop maintenance-copilot`), ask again, and confirm the fail-closed "unavailable" card appears and the agent does not freelance.

- [ ] **Step 5: Commit a note (optional)**

```bash
git commit --allow-empty -m "test(maintenance_copilot): phase-2 real-API e2e verified (proxy + card + guardrail)"
```

---

# Phase 3 — Federation host

Goal: add Module Federation to the web-ui host with **runtime** remote registration, validated by a throwaway hello-world remote before touching the real dashboard.

### Task 3.1: Add the federation plugin + runtime deps to the host

**Files:**
- Modify: `web-ui/package.json`
- Modify: `web-ui/vite.config.ts`

**Interfaces:**
- Produces: a host build that shares `react`/`react-dom` as singletons and can accept runtime-registered remotes (no static remotes declared).

- [ ] **Step 1: Install the deps**

```bash
cd web-ui
pnpm add @module-federation/vite @module-federation/runtime
```

- [ ] **Step 2: Wire the plugin into `vite.config.ts`**

Add the import and plugin (keep existing React/Tailwind plugins):

```typescript
import { federation } from '@module-federation/vite';

// ...inside plugins: [ ... ]
    federation({
      name: 'minder_host',
      // No static remotes: modules are registered at runtime from their manifests.
      remotes: {},
      shared: {
        react: { singleton: true, requiredVersion: '^18.3.1' },
        'react-dom': { singleton: true, requiredVersion: '^18.3.1' },
      },
      filename: 'remoteEntry.js',
    }),
```

- [ ] **Step 3: Verify the host still builds**

```bash
pnpm --dir web-ui build
```
Expected: build succeeds (federation runtime injected; no remotes yet).

- [ ] **Step 4: Commit**

```bash
cd /Users/anlnm/Desktop/Project/opendev-py
git add web-ui/package.json web-ui/pnpm-lock.yaml web-ui/vite.config.ts
git commit -m "feat(web-ui): add Module Federation host (runtime remotes, shared react)"
```

---

### Task 3.2: Runtime remote registration helper + hello-world validation

**Files:**
- Create: `web-ui/src/lib/federation.ts`
- Create (throwaway): `web-ui/src/lib/federation.hello.test.ts`

**Interfaces:**
- Produces:
  - `registerRemote(opts: {name: string; entry: string}): void` — idempotent runtime `registerRemotes`.
  - `loadRemoteComponent(name: string, exposed: string): Promise<React.ComponentType<any>>` — `loadRemote(\`${name}/${exposed}\`)` returning the default export.
- Consumed by: Task 4.3 (dashboard render branch).

- [ ] **Step 1: Write the failing test (mock the runtime)**

Create `web-ui/src/lib/federation.hello.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';

const registerRemotes = vi.fn();
const loadRemote = vi.fn();
vi.mock('@module-federation/runtime', () => ({
  registerRemotes: (...a: unknown[]) => registerRemotes(...a),
  loadRemote: (...a: unknown[]) => loadRemote(...a),
  init: vi.fn(),
}));

describe('federation helper', () => {
  beforeEach(() => { registerRemotes.mockClear(); loadRemote.mockClear(); });

  it('registers a remote by name+entry', async () => {
    const { registerRemote } = await import('./federation');
    registerRemote({ name: 'maintenance_copilot', entry: 'http://localhost:9200/dashboard/remoteEntry.js' });
    expect(registerRemotes).toHaveBeenCalledWith(
      [{ name: 'maintenance_copilot', entry: 'http://localhost:9200/dashboard/remoteEntry.js' }],
      { force: true },
    );
  });

  it('loads an exposed component and returns its default export', async () => {
    const Dummy = () => null;
    loadRemote.mockResolvedValue({ default: Dummy });
    const { loadRemoteComponent } = await import('./federation');
    const Comp = await loadRemoteComponent('maintenance_copilot', './Dashboard');
    expect(loadRemote).toHaveBeenCalledWith('maintenance_copilot/Dashboard');
    expect(Comp).toBe(Dummy);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir web-ui test src/lib/federation.hello.test.ts`
Expected: FAIL — `./federation` does not exist.

- [ ] **Step 3: Create `federation.ts`**

Create `web-ui/src/lib/federation.ts`:

```typescript
import { registerRemotes, loadRemote } from '@module-federation/runtime';
import type { ComponentType } from 'react';

const registered = new Set<string>();

/** Idempotently register a module's federation remote by name + remoteEntry URL. */
export function registerRemote(opts: { name: string; entry: string }): void {
  if (registered.has(opts.name)) return;
  registerRemotes([{ name: opts.name, entry: opts.entry }], { force: true });
  registered.add(opts.name);
}

/** Load an exposed module (e.g. './Dashboard') and return its default export. */
export async function loadRemoteComponent(
  name: string,
  exposed: string,
): Promise<ComponentType<any>> {
  const mod = (await loadRemote(`${name}/${exposed.replace(/^\.\//, '')}`)) as {
    default: ComponentType<any>;
  } | null;
  if (!mod || !mod.default) {
    throw new Error(`remote ${name}/${exposed} has no default export`);
  }
  return mod.default;
}
```

> NOTE: `loadRemote` takes `name/exposedKey`; the plugin normalizes exposed keys, so `'./Dashboard'` is addressed as `maintenance_copilot/Dashboard`. The `.replace(/^\.\//,'')` strips the leading `./`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir web-ui test src/lib/federation.hello.test.ts`
Expected: PASS.

- [ ] **Step 5: Manual hello-world validation (the risky-piece gate)**

Before Phase 4, prove a real runtime remote loads end-to-end:
1. Scaffold a throwaway Vite remote in `/tmp/hello-remote` with `@module-federation/vite`, `name: 'hello'`, `exposes: { './Widget': './src/Widget.tsx' }`, `shared: ['react','react-dom']`, served on `:9300`.
2. In the running web-ui, from the browser console: `import('/src/lib/federation.ts').then(m => { m.registerRemote({name:'hello', entry:'http://localhost:9300/remoteEntry.js'}); return m.loadRemoteComponent('hello','./Widget'); }).then(c => console.log('loaded', c))`.
3. Confirm `loaded [Function]` logs with no React-singleton duplication warning.

Expected: the remote component loads and shares the host's React. If singleton warnings appear, pin `requiredVersion` to match `web-ui`'s exact React version. Delete `/tmp/hello-remote` after.

- [ ] **Step 6: Commit (keep the helper; the hello test stays as a regression guard)**

```bash
git add web-ui/src/lib/federation.ts web-ui/src/lib/federation.hello.test.ts
git commit -m "feat(web-ui): runtime remote registration helper (federation.ts)"
```

---

# Phase 4 — Federated dashboard (retire the iframe for this module)

Goal: `maintenance_copilot` ships its own React dashboard as a federation remote, rendered natively in-host, sharing the host's WebSocket + store. The iframe path is bypassed for this module.

### Task 4.1: Build the module's frontend remote

**Files:**
- Create: `modules/maintenance_copilot/frontend/package.json`
- Create: `modules/maintenance_copilot/frontend/vite.config.ts`
- Create: `modules/maintenance_copilot/frontend/src/DashboardApp.tsx`
- Create: `modules/maintenance_copilot/frontend/index.html`

**Interfaces:**
- Produces: a built `remoteEntry.js` exposing `./Dashboard` (a `React.ComponentType<{ apiBase: string }>`), served by the backend at `/dashboard/remoteEntry.js`.

- [ ] **Step 1: Create the remote's `package.json`**

Create `modules/maintenance_copilot/frontend/package.json`:

```json
{
  "name": "maintenance-copilot-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "vite build",
    "dev": "vite"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@module-federation/vite": "^1.4.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.4.0",
    "vite": "^5.1.4"
  }
}
```

- [ ] **Step 2: Create the remote's `vite.config.ts`**

Create `modules/maintenance_copilot/frontend/vite.config.ts`:

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { federation } from '@module-federation/vite';

export default defineConfig({
  plugins: [
    react(),
    federation({
      name: 'maintenance_copilot',
      filename: 'remoteEntry.js',
      exposes: {
        './Dashboard': './src/DashboardApp.tsx',
      },
      shared: {
        react: { singleton: true, requiredVersion: '^18.3.1' },
        'react-dom': { singleton: true, requiredVersion: '^18.3.1' },
      },
    }),
  ],
  build: {
    // Emitted into the image and served by app.py at /dashboard/*
    outDir: 'dist',
    target: 'esnext',
  },
  server: { origin: 'http://localhost:9200' },
});
```

- [ ] **Step 3: Create the exposed dashboard component**

Create `modules/maintenance_copilot/frontend/src/DashboardApp.tsx`:

```tsx
import { useEffect, useState } from 'react';

interface DashboardProps {
  /** Connector public base, e.g. http://localhost:9200 — passed by the host. */
  apiBase: string;
}

interface HealthState {
  ok: boolean;
  module?: string;
}

/**
 * The maintenance_copilot dashboard, rendered natively inside the Minder host
 * via Module Federation (no iframe). Starts minimal: a live health panel + a
 * grounded-query box hitting the connector's /connector/run 'retrieve' action.
 */
export default function DashboardApp({ apiBase }: DashboardProps) {
  const [health, setHealth] = useState<HealthState | null>(null);
  const [q, setQ] = useState('');
  const [answer, setAnswer] = useState<string>('');

  useEffect(() => {
    fetch(`${apiBase}/connector/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ ok: false }));
  }, [apiBase]);

  async function retrieve() {
    const r = await fetch(`${apiBase}/connector/run`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action: 'retrieve', args: { query: q } }),
    });
    const card = await r.json();
    setAnswer(card.answer ?? '(no answer)');
  }

  return (
    <div style={{ padding: 16 }}>
      <h2>Maintenance Copilot</h2>
      <p>Service: {health ? (health.ok ? 'online' : 'offline') : 'checking…'}</p>
      <input value={q} onChange={(e) => setQ(e.target.value)}
             placeholder="Ask a maintenance question…" style={{ width: '70%' }} />
      <button onClick={retrieve} disabled={!q.trim()}>Retrieve</button>
      {answer && <pre style={{ whiteSpace: 'pre-wrap' }}>{answer}</pre>}
    </div>
  );
}
```

- [ ] **Step 4: Create `index.html` (dev harness) and build**

Create `modules/maintenance_copilot/frontend/index.html`:

```html
<!doctype html>
<html><head><meta charset="utf-8" /><title>mc remote</title></head>
<body><div id="root"></div></body></html>
```

Run:
```bash
cd modules/maintenance_copilot/frontend && pnpm install && pnpm build
ls dist/remoteEntry.js
```
Expected: `dist/remoteEntry.js` exists.

- [ ] **Step 5: Serve the built remote from the backend**

In `modules/maintenance_copilot/backend/app.py`, mount the built frontend (add near the bottom):

```python
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_DASHBOARD_DIST = Path(os.environ.get("MC_DASHBOARD_DIST", "/app/frontend_dist"))
if _DASHBOARD_DIST.is_dir():
    app.mount("/dashboard", StaticFiles(directory=str(_DASHBOARD_DIST)), name="dashboard")
```

And in the `Dockerfile`, add a frontend build stage before the final copy (multi-stage):

```dockerfile
# --- frontend build stage ---
FROM node:20-slim AS fe
WORKDIR /fe
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN corepack enable && pnpm install
COPY frontend/ ./
RUN pnpm build
# --- (in the python stage, after COPY . /app) ---
# COPY --from=fe /fe/dist /app/frontend_dist
```

Add `COPY --from=fe /fe/dist /app/frontend_dist` to the python stage of the Dockerfile.

- [ ] **Step 6: Commit**

```bash
cd /Users/anlnm/Desktop/Project/opendev-py
git add modules/maintenance_copilot/frontend modules/maintenance_copilot/backend/app.py modules/maintenance_copilot/backend/Dockerfile
git commit -m "feat(maintenance_copilot): federation remote frontend (./Dashboard) served by backend"
```

---

### Task 4.2: Surface `remote` fields to the web-ui

**Files:**
- Modify: `minder/web/routes/modules.py`
- Modify: `web-ui/src/types/index.ts`
- Modify: `web-ui/src/api/modules.ts`
- Modify: `web-ui/src/stores/modules.ts`

**Interfaces:**
- Produces: each dashboard summary the UI receives gains `remote: boolean`, `remote_name: string | null`, `remote_entry: string | null`, `remote_dashboard: string | null` (the exposed key, e.g. `./Dashboard`), `api_base: string | null`.
- Consumed by: Task 4.3.

- [ ] **Step 1: Add remote fields in the backend dashboards route**

In `minder/web/routes/modules.py`, find where a module's dashboard summary dict is built (search `dashboard_title` / the list of `modulesWithDashboards`). For each module, read `module.manifest.remote` and include:

```python
        remote = getattr(m.manifest, "remote", None) if m.manifest else None
        summary["remote"] = remote is not None
        summary["remote_name"] = remote.name if remote else None
        summary["remote_entry"] = remote.remote_entry if remote else None
        summary["remote_dashboard"] = (remote.exposed.get("dashboard") if remote else None)
        svc = getattr(m.manifest, "service", None) if m.manifest else None
        # Browser-facing base for fetches from the federated component.
        summary["api_base"] = (remote.remote_entry.split("/dashboard/")[0]
                               if remote else None)
```

- [ ] **Step 2: Extend the web-ui type + store**

In `web-ui/src/types/index.ts`, add to the module dashboard summary interface (search for `dashboard_title`):

```typescript
  remote?: boolean;
  remote_name?: string | null;
  remote_entry?: string | null;
  remote_dashboard?: string | null;
  api_base?: string | null;
```

Ensure `web-ui/src/api/modules.ts` passes these through (if it maps fields explicitly, add them; if it spreads the response, no change needed). Confirm `web-ui/src/stores/modules.ts` `modulesWithDashboards` carries the new fields (again, spread → no change; explicit map → add fields).

- [ ] **Step 3: Verify build**

```bash
pnpm --dir web-ui build
uv run --no-sync pytest tests/ -k "modules_route or module_dashboard" -q
```
Expected: builds; route tests pass (new fields are additive).

- [ ] **Step 4: Commit**

```bash
git add minder/web/routes/modules.py web-ui/src/types/index.ts web-ui/src/api/modules.ts web-ui/src/stores/modules.ts
git commit -m "feat(modules): surface remote/federation fields to the web-ui"
```

---

### Task 4.3: `ModuleDashboardView` remote branch — render the federated dashboard in-host

**Files:**
- Modify: `web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx`
- Create: `web-ui/src/components/ModuleDashboard/RemoteDashboard.tsx`
- Test: `web-ui/src/components/ModuleDashboard/RemoteDashboard.test.tsx`

**Interfaces:**
- Consumes: `registerRemote`, `loadRemoteComponent` (`src/lib/federation.ts`); the summary's `remote_*`/`api_base` fields.
- Produces: `<RemoteDashboard summary={...} />` that registers the remote, loads its `./Dashboard`, and renders it with `apiBase` prop. `ModuleDashboardView` renders `<RemoteDashboard>` when `summary.remote`, else the existing iframe.

- [ ] **Step 1: Write the failing test**

Create `web-ui/src/components/ModuleDashboard/RemoteDashboard.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('../../lib/federation', () => ({
  registerRemote: vi.fn(),
  loadRemoteComponent: vi.fn(async () =>
    ({ apiBase }: { apiBase: string }) => <div>remote-ok:{apiBase}</div>),
}));

import { RemoteDashboard } from './RemoteDashboard';

describe('RemoteDashboard', () => {
  it('registers the remote and renders the loaded component with apiBase', async () => {
    const fed = await import('../../lib/federation');
    render(<RemoteDashboard summary={{
      name: 'maintenance_copilot', remote: true, remote_name: 'maintenance_copilot',
      remote_entry: 'http://localhost:9200/dashboard/remoteEntry.js',
      remote_dashboard: './Dashboard', api_base: 'http://localhost:9200',
    } as any} />);
    await waitFor(() => expect(screen.getByText(/remote-ok:http:\/\/localhost:9200/)).toBeInTheDocument());
    expect(fed.registerRemote).toHaveBeenCalledWith({
      name: 'maintenance_copilot',
      entry: 'http://localhost:9200/dashboard/remoteEntry.js',
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir web-ui test src/components/ModuleDashboard/RemoteDashboard.test.tsx`
Expected: FAIL — `RemoteDashboard` does not exist.

- [ ] **Step 3: Create `RemoteDashboard.tsx`**

Create `web-ui/src/components/ModuleDashboard/RemoteDashboard.tsx`:

```tsx
import { useEffect, useState, type ComponentType } from 'react';
import { registerRemote, loadRemoteComponent } from '../../lib/federation';

interface RemoteSummary {
  name: string;
  remote?: boolean;
  remote_name?: string | null;
  remote_entry?: string | null;
  remote_dashboard?: string | null;
  api_base?: string | null;
}

/**
 * Loads a service-module's federated dashboard remote and renders it natively
 * in-host (no iframe), sharing the host's React. The remote receives `apiBase`
 * so its own fetches hit the module's connector directly.
 */
export function RemoteDashboard({ summary }: { summary: RemoteSummary }) {
  const [Comp, setComp] = useState<ComponentType<any> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    if (!summary.remote_name || !summary.remote_entry || !summary.remote_dashboard) {
      setError('module is missing federation remote fields');
      return;
    }
    registerRemote({ name: summary.remote_name, entry: summary.remote_entry });
    loadRemoteComponent(summary.remote_name, summary.remote_dashboard)
      .then((c) => { if (alive) setComp(() => c); })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [summary.remote_name, summary.remote_entry, summary.remote_dashboard]);

  if (error) return <div className="p-4 text-sm text-red-400">Dashboard failed: {error}</div>;
  if (!Comp) return <div className="p-4 text-sm text-text-300">Loading dashboard…</div>;
  return <Comp apiBase={summary.api_base ?? ''} />;
}
```

- [ ] **Step 4: Branch in `ModuleDashboardView`**

In `web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx`, import and short-circuit to the remote branch when the summary is remote. Add the import and, right after `summary` is resolved (after the `const summary = useModulesStore(...)` line), before the iframe JSX:

```tsx
import { RemoteDashboard } from './RemoteDashboard';

// ...after summary is resolved:
  if (summary?.remote) {
    return (
      <div className="flex h-full w-full flex-col bg-bg-000">
        <header className="flex items-center gap-3 px-4 py-2 border-b border-border-300/15 bg-bg-100">
          <button type="button" onClick={closeDashboard}
                  className="flex items-center gap-1.5 text-xs text-text-300 hover:text-text-100 transition-colors"
                  aria-label="Back to chat">
            <ArrowLeft className="h-3.5 w-3.5" /> Back
          </button>
          <span className="text-sm text-text-100">{title}</span>
        </header>
        <div className="flex-1 overflow-auto">
          <RemoteDashboard summary={summary as any} />
        </div>
      </div>
    );
  }
```

The existing iframe return stays below as the fallback for non-remote modules.

- [ ] **Step 5: Run tests + build**

```bash
pnpm --dir web-ui test src/components/ModuleDashboard/RemoteDashboard.test.tsx
pnpm --dir web-ui build
```
Expected: PASS + build succeeds.

- [ ] **Step 6: Commit**

```bash
git add web-ui/src/components/ModuleDashboard/RemoteDashboard.tsx web-ui/src/components/ModuleDashboard/RemoteDashboard.test.tsx web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx
git commit -m "feat(web-ui): render federated module dashboard in-host (retire iframe for remote modules)"
```

---

### Task 4.4: Update the manifest + full-stack e2e verification

**Files:**
- Modify: `modules/maintenance_copilot/manifest.json`

- [ ] **Step 1: Add the `service` + `remote` blocks to the manifest**

Edit `modules/maintenance_copilot/manifest.json` to add (alongside the existing keys):

```json
  "service": {
    "connector_url": "http://maintenance-copilot:9200",
    "health_path": "/connector/health",
    "tools": [
      {
        "name": "maintenance_copilot_query",
        "description": "Answer an aircraft-maintenance question (AMM/MEL/CDL/TSM/defect/dispatch/ATA) with grounded RAG: returns a cited, confidence-scored answer and renders it as a maintenance-answer card in the UI. Advisory only — never a dispatch decision.",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {"type": "string", "description": "The maintenance question, in English."},
            "k": {"type": "integer", "default": 5, "description": "Passages to retrieve."},
            "ata": {"type": "string", "description": "Optional ATA chapter filter, e.g. '32'."},
            "revision": {"type": "string", "default": "current", "description": "'current', a specific revision, or 'none'."}
          },
          "required": ["query"]
        }
      }
    ]
  },
  "remote": {
    "name": "maintenance_copilot",
    "remoteEntry": "http://localhost:9200/dashboard/remoteEntry.js",
    "exposed": {"dashboard": "./Dashboard", "cards": {"maintenance_answer": "./MaintenanceAnswerCard"}}
  }
```

- [ ] **Step 2: Full-stack bring-up**

```bash
export OPENAI_API_KEY="<real key>"
docker compose up -d --build maintenance-copilot qdrant neo4j minder
pnpm --dir web-ui build   # host with federation
```

- [ ] **Step 3: Real e2e — agent tool + native dashboard**

1. Open the web UI. Ask a maintenance question → confirm the `maintenance_answer` card renders (via the proxy tool broadcast).
2. Open the maintenance_copilot dashboard → confirm it loads **natively** (React DevTools shows the remote component in the host tree, NOT an iframe), the health panel shows "online", and a retrieve query returns a grounded answer.
3. Stop the service → dashboard shows offline / query fails closed; agent question returns the unavailable card and does NOT read the corpus.

- [ ] **Step 4: Confirm the dep-isolation win**

```bash
docker compose exec minder python -c "import importlib.util as u; \
print('qdrant-client in minder image:', u.find_spec('qdrant_client') is not None)"
```
Expected: `False` — the Minder image no longer carries the module's heavy deps.

- [ ] **Step 5: Run the full Python suite once (per user's batch-test preference)**

```bash
uv run --no-sync pytest tests/ -q
```
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add modules/maintenance_copilot/manifest.json
git commit -m "feat(maintenance_copilot): declare service + remote manifest blocks (federation live)"
```

---

## Self-Review Notes (author)

- **Spec coverage:** §Architecture-1 (layout) → 1.1/1.4/4.1; §2 (connector contract) → 1.3; §3 (remote registry + proxy + card broadcast + unavailable stub) → 2.2/2.3/2.4; §4 (compose supervise) → 1.4/2.5; §5 (federation host + remote + native render + card) → 3.1/3.2/4.1/4.3 (dashboard) — **see deviation below on the card**; §6 phasing → phase split matches; §7 testing → 1.x unit + 2.5/4.4 real e2e; §8 risks → 3.2 hello-world gate, singleton pinning (3.1/4.1), fail-closed (2.3), CORS (1.3 middleware + `api_base` split 4.2).
- **Deviation to confirm with user (surfaced at handoff):** the spec lists a *federated `maintenance_answer` card*. The card already renders **natively** today as a host React component (`MaintenanceAnswerBlock.tsx`) fed by the unchanged `maintenance_answer` broadcast — it is NOT iframe-bound. This plan keeps that host card (fed by the connector's `card` payload) and federates only the **dashboard** (the genuinely iframe-bound surface), deferring card-federation as YAGNI. The manifest still declares the `MaintenanceAnswerCard` exposed key so card-federation can be added later without a contract change.
- **Type consistency:** card dict shape identical across `service.run_query`, `service.unavailable_payload`, and `remote.unavailable_card`; broadcast type `maintenance_answer` unchanged end-to-end; `registerRemote`/`loadRemoteComponent` signatures match between `federation.ts`, its test, and `RemoteDashboard`.
