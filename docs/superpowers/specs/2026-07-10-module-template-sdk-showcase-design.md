# module_template — SDK Showcase Module — Design

**Date:** 2026-07-10
**Status:** Approved (design), pending implementation plan
**Builds on:** the SDK Integration Enhancements branch (`feat/federated-chat-blocks`). This adds a runnable reference module that exercises every SDK capability, closes the deferred `ctx.principal` wiring, and refreshes the integration guide.

## Goal

Ship `modules/module_template/` — a full, runnable service-module whose sole purpose
is to **introduce itself to the agent and demonstrate every `minder_python_sdk`
capability** when asked. It doubles as the copy-me skeleton for building new modules.
Also wire `ctx.principal` at the host so `requires_auth` works for real, and update
`modules/module_integration.md` to match the current SDK.

## Non-goals

- Heavy dependencies. `module_template` uses fake/in-memory data only — it showcases
  the SDK surface, not a real domain pipeline.
- Replacing `maintenance_copilot` as a reference (it stays the real-world example;
  `module_template` is the exhaustive SDK-feature example).
- MCP (separate track).

## Part 1 — Host: wire `ctx.principal` (closes the deferred limitation)

Today `SkillToolContext.principal` is left `None` on the agent-tool path (no acting
user in the broadcaster's scope), so `requires_auth` always sees anonymous.

- **`minder/web/ws_tool_broadcaster.py`:** `WebSocketToolBroadcaster.__init__` gains a
  `principal: Optional[dict] = None` param (stored as `self.principal`); in the
  `if skill_ctx is not None:` block, set `skill_ctx.principal = self.principal`.
- **`minder/web/agent_executor.py`** (~line 330, where the broadcaster is constructed):
  compute `owner = getattr(session, "owner_id", "") or ""` and pass
  `principal=({"username": owner, "email": ""} if owner else None)`. When there is no
  owner (single-user / anonymous mode), principal stays `None` → `requires_auth` tools
  fail closed (correct).
- **`minder/core/modules/remote.py`:** update the now-stale `_make_handler` comment
  ("agent tool calls carry no user identity") to state that identity is forwarded from
  the session's owner.
- **Test:** with a broadcaster constructed with `principal={"username": "alice", "email": ""}`,
  the wired `skill_ctx.principal` is forwarded as `X-Minder-Principal` on a tool call
  (extend `tests/test_ctx_identity_forwarding.py`).
- **Identity note:** `owner_id` is used as the principal identity. If a user-service
  mapping `owner_id → {username, email}` exists later, upgrade to it; `owner_id` is the
  grounded value available at this call site now.

## Part 2 — `modules/module_template/` (runnable SDK showcase)

Each tool demonstrates exactly one capability. Backend logic is pure and fake — no
`minder` import anywhere in the module.

### backend/app.py — tools

- **`template_typed_query`** — `@conn.tool(params_model=TemplateQuery)` where
  `TemplateQuery(BaseModel)` has `topic: str`, `limit: int = 3`. Demonstrates
  pydantic-derived schema + validation. Returns a `card(...)`.
- **`template_card`** — returns `card(answer, confidence=…, validation_warnings=[…],
  card_type="template_card")`; renders via the generic card renderer.
- **`template_block`** — returns `{"output": text, "blocks": [conn.block("./ShowcaseBlock",
  props)]}`; the module's own federated React block.
- **`template_stream`** — `streaming=True` generator: `yield {"event":"progress","message":
  "step 1…","pct":30}` → `yield {"event":"block","block": conn.block("./ShowcaseBlock",
  props)}` → `yield {"event":"final","success":True,"output":summary}`. Demonstrates
  streaming + mid-stream block push.
- **`template_secure`** — `@conn.tool(requires_auth=True)`; a handler that reads
  `principal` and returns who called it. Blocked (structured "authentication required")
  for anonymous; runs for an authenticated principal (works now that Part 1 wires it).
- **`template_async_job`** — signature `(steps: int = 3, session_id=None)`. Returns
  immediately with an ack, then a daemon thread uses `conn.minder_client()` to
  `push_block("./ShowcaseBlock", {"pct":0})`, `update_block(...)` per step, and finally
  `update_block(..., {"pct":100,"done":True})`. Demonstrates reverse-push + `session_id`.
  No-ops gracefully (logs) if `minder_client()` raises `MinderClientError` (unconfigured).
- **`template_export`** — signature `(session_id=None)`. Renders a small markdown report
  and `conn.minder_client().push_artifact(session_id, "template_report.md", bytes)`;
  returns the artifact id. Demonstrates `push_artifact` + `session_id`.

### backend/app.py — lifecycle & registration

- `@conn.readiness_probe` — returns `{"ready": _warmed_up()}`; a module-level flag flips
  True a couple seconds after boot (simulated warm-up), so the module demonstrates
  tools staying hidden until ready.
- `@conn.health_probe` — `{"showcase": "ok"}`.
- `@conn.on_startup` — logs a banner + sets the warm-up flag after a short sleep.
- `@conn.route("/ping", methods=["GET"])` — returns `{"pong": principal.username}` (extra
  endpoint via the generic passthrough; takes `principal`).
- `conn.expose_block("./ShowcaseBlock")` and `Connector(..., min_core_version="2")`.
- `app = conn.asgi()`.

### backend/service.py

Pure fake logic: `search(topic, limit) -> dict`, `report_markdown() -> str`, small
in-memory data. Never imports `minder`.

### frontend/

- `src/ShowcaseBlock.tsx` — default export `ShowcaseBlock(props)`, consumes
  `{...props, apiBase, bridge}`; renders the payload and has buttons calling
  `bridge.toast(...)` and `bridge.sendMessage(...)` to demonstrate the host bridge.
- `src/DashboardApp.tsx` — `{apiBase}`; lists the showcase tools and calls
  `${apiBase}/connector/tools/...` / `${apiBase}/connector/ping`.
- `vite.config.ts` — Module Federation `name: "module_template"`, exposes
  `{"./Dashboard": "./src/DashboardApp.tsx", "./ShowcaseBlock": "./src/ShowcaseBlock.tsx"}`,
  `react`/`react-dom` singletons `^18.3.1`.
- `package.json`, `tsconfig.json`, `index.html`.

### Module metadata & deploy

- `SKILL.md` — frontmatter `name: module_template`, a `description` telling the agent to
  use it to see/demo SDK capabilities, and a when/how-to-use body listing each tool.
- `manifest.json` — presentation (`display_name`, `dashboard`, `remote` with browser
  `remoteEntry`), no domain corpus.
- `icon.svg`, `Dockerfile` (multi-stage: build frontend → slim python, installs
  `minder-python-sdk`), `docker-compose.snippet.yml` (env: `MINDER_URL`,
  `MINDER_MODULE_CONNECTOR_URL`, `MINDER_MODULE_REMOTE_ENTRY`, `MODULE_PUBLIC_BASE`, Keycloak
  client creds), `README.md` mapping each SDK feature to the code that uses it.
- `backend/tests/test_template.py` — uses `conn.invoke(...)` to exercise
  `template_typed_query` (valid + invalid), `template_secure` (anon blocked vs authed),
  and asserts the manifest advertises `./ShowcaseBlock` + `min_core_version`.

## Part 3 — Docs

Update `modules/module_integration.md`:
- Point to `module_template` as the exhaustive SDK-feature showcase (alongside
  `maintenance_copilot` as the real-world example).
- Add/refresh sections for the capabilities not yet covered: `params_model`,
  `@readiness_probe`, `requires_auth`, `conn.invoke`, `conn.block` (already present),
  `expose_block` + manifest enrichment, streaming `block` events, and the `MinderClient`
  reverse-push + `push_artifact` outbound channel (with the `module-push` role note).

## Constraints

- The module never imports `minder`; `MinderClient` uses httpx + env only.
- Reverse-push + artifact push require the `module-push` role (the `minder-module` client
  already holds it); the template's compose snippet documents the env.
- `requires_auth` fail-closed / `params_model` invalid → structured `{success: False}`,
  never a 500.
- React `singleton` in the module frontend; host CSS tokens are available in-host.
- No `Co-Authored-By: Claude` trailer. Test command `uv run --no-sync pytest`.
- `docs/` + `tests/` gitignored — `git add -f` for spec/plan and new host test files;
  the module's own `backend/tests/` lives under `modules/` (tracked normally).

## Testing

- Host: extend `tests/test_ctx_identity_forwarding.py` for the wired principal.
- Module: `backend/tests/test_template.py` via `conn.invoke` (typed query, secure gate,
  manifest).
- E2E (deferred to user, per CLAUDE.md, needs `OPENAI_API_KEY` + running container):
  ask the agent to demo each capability; verify the card, federated block, streaming
  progress, `requires_auth` behavior, async reverse-push progress block, and the
  exported artifact all appear in chat.
