# module_template — atria-module-sdk showcase

A runnable module that exercises every SDK capability. Copy it to bootstrap a new module.

## Feature → code

- **params_model (typed params)** — `template_typed_query` + `TemplateQuery` in `backend/app.py`.
- **card()** — `template_card`.
- **conn.block() federated block** — `template_block` + `frontend/src/ShowcaseBlock.tsx`.
- **streaming + mid-stream block event** — `template_stream`.
- **requires_auth** — `template_secure` (needs an authenticated principal).
- **AtriaClient reverse-push (push/update block)** — `template_async_job` (background thread).
- **push_artifact** — `template_export`.
- **readiness_probe / health_probe / on_startup** — the lifecycle hooks in `app.py`.
- **@conn.route (generic passthrough)** — `/ping`.
- **expose_block + min_core_version** — `conn.expose_block(...)` + `Connector(min_core_version=...)`.
- **conn.invoke (in-process testing)** — `backend/tests/test_template.py`.

## Run

`atria-module dev module_template` for local iteration, or paste
`docker-compose.snippet.yml` into `docker-compose.yml` and `docker compose up -d --build module-template`.
See `modules/module_integration.md` for the full contract + required env.
