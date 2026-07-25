# Task 16 Report: Web routes (rescan + list) and scheduler wiring

## Files Changed

- **Created**: `minder/web/routes/knowledge.py` — `build_router(service_factory, tenant_factory, seed_scan)` with `GET /knowledge/documents` and `POST /knowledge/rescan`.
- **Modified**: `minder/core/knowledge/wiring.py` — added `_default_chat_fn()`, `_knowledge_seed_and_drain()`, `build_knowledge_service()`, `run_seed_scan()`.
- **Modified**: `minder/web/server.py` — added knowledge router inclusion in `create_app()` and scheduler registration in `lifespan()`.
- **Created**: `tests/knowledge/test_web_routes.py` — two tests for the router.

## App Factory File

`minder/web/server.py`. The `create_app()` function registers the knowledge router (wrapped in try/except so a missing DB never crashes startup). The `lifespan()` async context manager registers and starts a `BackgroundScheduler` with two tasks after `init_schema()`:
- `knowledge_drain` (30s interval): runs `_knowledge_seed_and_drain()` via `asyncio.ensure_future`.
- `knowledge_seed` (3600s interval): runs `_knowledge_seed_and_drain()` directly as an async callable.

The scheduler is stopped on shutdown via `scheduler.stop_all()` in the `finally` block.

## `_default_chat_fn` Implementation

Uses the `openai.OpenAI` SDK (already a project dependency, confirmed by `llm_wiring.py`). Reads `OPENAI_API_KEY`, `MINDER_API_BASE_URL` (with `SEARCH_EMBED_BASE_URL` as a fallback), and `MINDER_MODEL` from the environment. Strips any trailing `/chat/completions` suffix from the base URL to match what the SDK expects. Returns a zero-argument factory that builds the client and sends messages.

## Concerns

- `build_knowledge_service()` and `run_seed_scan()` both call `asyncio.run(get_sessionmaker())` which will fail if called from an already-running async context (e.g., from within a FastAPI route handler directly). This is intentional for the scheduler (runs in background threads), but the route handler uses `service_factory=build_knowledge_service` which is called synchronously from the async endpoint. If `get_sessionmaker()` is already initialized and cached, this may work; if it needs a fresh `asyncio.run()` call from within an async handler, it will raise. This matches the brief's code verbatim — the risk is noted.
- The scheduler's `knowledge_drain` task wraps `_knowledge_seed_and_drain` with `asyncio.ensure_future`, which requires a running event loop. Since `PeriodicTask._run` is itself a coroutine scheduled via `asyncio.create_task`, the `asyncio.ensure_future` call happens within the event loop — this is safe.

## Test Summary

2 passed (test_list_documents_endpoint, test_rescan_endpoint_reports_counts). All 44 knowledge tests pass. Server imports cleanly.
