# Fix Wave Final Report

## Status

DONE

## Commit

`3554c53` on `feat/service-module-federation`

All 9 files in one commit:
- `minder/web/routes/maintenance.py` — full rewrite, connector proxy
- `minder/core/modules/remote.py` — added `get_json` / `post_json`
- `modules/maintenance_copilot/backend/service.py` — added `sidecar_health` + `record_signoff`; removed unused `Any` import; added `advisory_note` key-rename comment
- `modules/maintenance_copilot/backend/app.py` — added `/connector/sidecar-health` + `/connector/signoff` endpoints; dropped dead `cards` from `exposed`
- `modules/maintenance_copilot/manifest.json` — dropped `remote.exposed.cards`
- `docker-compose.yml` — added `MC_AUDIT_LOG` env + `mc_audit` named volume
- `web-ui/vite.config.ts` — removed `manualChunks` block
- `tests/test_connector_app.py` — appended two new tests
- `tests/test_maintenance_route.py` — new file, 2 tests

## pytest summary

```
46 passed, 9 warnings in 1.04s
```

## npm run build

SUCCEEDED — `✓ built in 8.56s` (warnings about chunk size and dynamic/static imports are pre-existing, not introduced by this change).

## grep confirmation — no pipeline import in maintenance.py

```
$ grep -n "copilot\|audit\|scripts\|sys.path" minder/web/routes/maintenance.py
1:"""Maintenance-copilot web endpoints — the licensed-engineer sign-off.
3:The copilot is advisory only; a licensed engineer must review a cited answer and
5:append-only audit trail the copilot writes, so the human-in-the-loop step is
28:    """Build a RemoteConnector from the maintenance_copilot module's manifest."""
30:        module = get_registry().get("maintenance_copilot")
32:        raise HTTPException(503, "maintenance_copilot module not loaded") from exc
35:        raise HTTPException(503, "maintenance_copilot is not configured as a service")
36:    return RemoteConnector("maintenance_copilot", svc.connector_url, svc.health_path)
62:    """Sidecar health, proxied from the maintenance_copilot connector service."""
66:        raise HTTPException(503, f"maintenance copilot service unreachable: {exc}") from exc
71:    """Record a licensed-engineer sign-off; the connector writes the audit trail."""
```

Only docstring/comment references. No `import copilot`, no `import audit`, no `sys.path`, no `scripts` path manipulation.

## Concerns

One minor deviation from the brief: the brief's `record_signoff` in service.py added `{"type": "signoff", **payload}` before calling `audit.append_event`, and app.py called `service.record_signoff(body.model_dump())`. This arrangement made the brief's test fail (`captured["type"]` absent) because the test monkeypatches `record_signoff` itself (bypassing the `type` injection). To make the brief's exact test pass, the `type: signoff` injection was moved to app.py's call site (`service.record_signoff({"type": "signoff", **body.model_dump()})`) and `record_signoff` in service.py was simplified to pass payload through directly to `audit.append_event`. The net runtime behaviour is identical; the audit event always contains `type: signoff`.

---

# Fix Report — Final Whole-Branch Review Critical/Important Findings

Date: 2026-07-17

## C1 — `asyncio.run()` in running event loop

**Files changed:**
- `minder/core/knowledge/wiring.py`: Added `abuild_knowledge_service()` and `arun_seed_scan()` async variants that `await get_sessionmaker()`. Sync wrappers retained for CLI/off-loop use only. `_knowledge_seed_and_drain()` updated to `await` the async variants.
- `minder/web/routes/knowledge.py`: `build_router` now accepts async callables; route handlers `await` them.
- `minder/web/server.py`: Router registration passes `abuild_knowledge_service` and `arun_seed_scan`. Scheduler `knowledge_drain` task simplified to `_knowledge_seed_and_drain` directly.
- `tests/knowledge/test_web_routes.py`: Updated fake factories to async callables.

## C2 — Invalid Neo4j Cypher variable-length bound

**File changed:** `minder/core/knowledge/graph.py` (`_expand`)
- Replaced `"...-[:RELATED_TO*1..$hops]-..."` with f-string `f"...-[:RELATED_TO*1..{safe_hops}]-..."` where `safe_hops = int(hops)`. Dropped `hops` from parameter dict.

## C3 — Tenant fallback auth hole

**File changed:** `minder/web/server.py`
- Extracted `_resolve_web_tenant(req)` helper that gates `KNOWLEDGE_DEV_TENANT` fallback on `MINDER_ENV == "dev"`. Production unauthenticated requests now get `None`.

## I1 — Graph-only hits scored 0.0 / dropped

**File changed:** `minder/core/knowledge/provider.py`
- Computed `_GRAPH_SCORE = max(min_fused_score * 0.5, 1e-6)`. `SearchHit.score` uses `fused.get(external_id, _GRAPH_SCORE)` so graph-only hits survive and rank below vector hits.

## I2 — `_tenant_id` never set on AssistantAgent

**File changed:** `minder/core/agents/assistant_agent.py`
- Added optional `tenant_id: str | None = None` param to `__init__`. Sets `self._tenant_id = tenant_id`.

## I3 — Hard-coded Vietnamese headings

**File changed:** `minder/core/knowledge/profile.py`
- Lifted headings to module-level constants `HEADING_BACKGROUND` and `HEADING_PERSONA`. Strings unchanged.

## I4 — `_default_chat_fn` config bypass

**File changed:** `minder/core/knowledge/wiring.py`
- Changed fallback default from `"gpt-4o-mini"` to `"gpt-4o"` to align with `AppConfig.model`. Docstring explains AppConfig unavailability.

## M1 — Guard artifact ingest

**File changed:** `minder/core/knowledge/artifact_bytes.py`
- Added one-line comment confirming v1 gap and that `IngestionService.ingest_document` catches `NotImplementedError`.

## M2 — Strengthen model test

**File changed:** `tests/knowledge/test_models.py`
- Added second session block querying `KnowledgeChunk` by `document_id` and asserting `text`/`citation`.

---

## Command outputs

### `uv run pytest tests/knowledge -q`
```
46 passed, 1 skipped, 2 warnings in 1.54s
```

### `uv run python -c "import minder.web.server"`
```
OK (exit 0, no errors)
```

### `uv run python -c "import minder.core.context_engineering.tools.registry"`
```
OK (exit 0, no errors)
```
