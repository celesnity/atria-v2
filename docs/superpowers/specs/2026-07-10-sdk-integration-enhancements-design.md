# SDK Integration Enhancements — Design

**Date:** 2026-07-10
**Status:** Approved (design), pending implementation plan
**Builds on:** `feat/federated-chat-blocks` — the SDK self-registering-modules work
(runtime announce, connector-liveness reconciler, federated chat blocks, host
`ctx.push_block`). This spec extends `atria_module_sdk` and adds minimal host
support to complete the inbound + **bidirectional** integration surface.

## Goal

Extend `atria_module_sdk` (and the minimal Atria host support it needs) so a module
author gets: (1) less boilerplate and in-process testability, (2) a readiness gate,
(3) a proactive **reverse-push** channel (blocks + artifacts) so a module can update
the chat outside a tool call, (4) identity/session on the agent-tool path, (5)
streaming blocks, (6) typed parameters, richer manifest, and declarative auth. The
SDK still **never imports `atria`**.

## Non-goals

- **MCP surface / MCP auto-registration.** Explicitly deferred to a separate interop
  track. This package keeps the bespoke connector contract as the primary (and only)
  path into Atria. Reasons: MCP carries no card/federated-block/dashboard/liveness
  concepts natively; and registering one module into the same Atria via both the
  connector proxy and MCP would double every tool. (Technically feasible later via
  MCP `structuredContent`/`_meta` UI extensions — out of scope here.)
- Replacing the connector contract, the announce/heartbeat mechanism, or the
  federated-block render path (all reused as-is).
- Typed-parameter enforcement for handlers that keep hand-written `parameters=` JSON
  Schema (that path stays; `params_model` is opt-in).

## Enhancement set (10 items across four sections)

### A. SDK ergonomics & DX (SDK-only unless noted)

- **A1 — `conn.block(component, props=None, *, height="auto", title=None) -> dict`.**
  A `Connector` method that fills `remote_name=self.name` and
  `remote_entry=os.environ.get("ATRIA_MODULE_REMOTE_ENTRY", "")`, delegating to the
  existing free `block(...)` (which stays). Removes the per-module `_answer_block`
  boilerplate.
- **A2 — `conn.invoke(tool_name, arguments, principal=None, session_id=None) -> dict`.**
  Public wrapper over `_call` so module authors unit-test a tool in-process (no
  `TestClient`). Returns the normalized envelope.
- **A3 — `@conn.readiness_probe`.** Registers a `() -> bool | {"ready": bool, "detail": str}`.
  `/connector/health` gains a `ready` field (default `True` when no probe). A probe
  that raises is treated as `ready=False`. **Host change:** the `ConnectorReconciler`
  keeps a connector at `PENDING` (tools stay out of the catalog) while
  `health.ready is False`, promoting to `READY` only when healthy AND ready.
- **A4 — `@conn.tool(..., params_model=<pydantic.BaseModel subclass>)`.** Opt-in. When
  given, the SDK derives `parameters` from `params_model.model_json_schema()` and
  validates the incoming `arguments` against it before calling the handler; a
  validation error returns `{success: False, output: "invalid arguments: …"}` (never
  500). Mutually exclusive with `parameters=`.
- **A5 — `@conn.tool(..., requires_auth=True)`.** When set and the forwarded
  `principal.is_authenticated` is `False`, the SDK returns
  `{success: False, output: "authentication required"}` without calling the handler.
  Depends on section B (principal forwarded on the agent-tool path).

### B. Identity & session on the agent-tool path (host + SDK)

Today `_make_handler` deliberately forwards no identity on the agent-tool path. This
section reverses that (first-party trust) to enable A5 and C1.

- **B1 — `SkillToolContext` gains `session_id: str | None` and `principal: dict | None`.**
  Mutable, wired by `ws_tool_broadcaster.py` at session setup — the same place and
  pattern as `broadcaster` / `push_block`.
- **B2 — `_make_handler` forwards identity.** It passes `ctx.principal` into
  `conn.call_tool(..., principal=…)` (the client already supports it) and adds a new
  header `X-Atria-Session: <session_id>`.
- **B3 — SDK reads session.** `_principal_from_headers` already parses
  `X-Atria-Principal`; add reading of `X-Atria-Session`. Handlers that declare
  `session_id` (or `**kwargs`) receive it, mirroring how `principal` is injected.
  Only `{username, email}` + `session_id` are forwarded — no sensitive token.

### C. Bidirectional outbound (SDK + one new host ingress)

- **C1 — `AtriaClient` (`atria_module_sdk/client.py`).** `conn.atria_client()` builds
  a client from `ATRIA_URL` + client-credentials (role `module-push`). Methods wrap
  the existing reverse-push ingress `/api/blocks/remote/{push,update,remove}`:
  - `push_block(session_id, component, props=None, *, remote_entry=None, height="auto", title=None, block_id=None) -> str` (returns `block_id`)
  - `update_block(session_id, block_id, props) -> None`
  - `remove_block(session_id, block_id) -> None`
  `remote_entry` defaults to `$ATRIA_MODULE_REMOTE_ENTRY`; `remote_name` = the
  connector name. Enables async jobs: capture `session_id` in a tool handler (§B),
  return immediately, then push/update a progress block from a daemon thread. **No
  host change** — the ingress and `ui_bridge.push_remote_block/update_block/remove_block`
  already exist.
- **C2 — `block` event in streaming.** The host `_run_stream` (in `remote.py`) gains a
  branch: an event `{"event": "block", "block": {…descriptor…}}` calls
  `ctx.push_block(block, conn.name)`. The SDK's `_sse` already forwards arbitrary
  `event` dicts, so a streaming handler can `yield {"event": "block", "block":
  conn.block("./X", props)}` mid-stream. **Host change:** the one `_run_stream` branch.
- **C3 — Artifact push (new host ingress).**
  - **Host:** `atria/web/routes/artifacts_remote.py` — `POST /api/artifacts/remote/push`
    gated by `require_service_principal` (role `module-push`); body
    `{session_id, filename, content_b64, type}`. It calls a new
    `ui_bridge.push_artifact(session_id, filename, content_b64, type)` that stores the
    artifact against the session (reusing the existing artifact store) and broadcasts
    an artifact-available WS event.
  - **SDK:** `AtriaClient.push_artifact(session_id, filename, content: bytes, type="report") -> int`
    (returns artifact id). For data/report modules to attach files/images to the chat.

### D. Manifest, roles, errors, testing

- **D1 — Manifest enrichment.** `conn.expose_block(component_key)` registers extra
  Module-Federation exposed components. `/connector/manifest` `remote.exposed` then
  lists `./Dashboard` plus each exposed block; the manifest also advertises
  `card_types` (union of the tools' `card_type`), `contract_version`
  (the SDK's connector-contract version), and `min_core_version`. Host reconciler may
  read these but is not required to act on them beyond `tools` (forward-compatible).
- **D2 — Keycloak roles.** Grant the `atria-module` service client BOTH realm roles
  in `keycloak/realm-export.json`: `module-register` (already present) and
  `module-push` (add), via `service-account-atria-module`.
- **D3 — Error handling (fail-closed preserved).** `requires_auth` reject →
  structured, no 500. `params_model` validation fail → structured, no 500.
  `readiness_probe` raising → `ready=False`. `AtriaClient` operations are proactive:
  on network/HTTP error they log and raise `AtriaClientError` (distinct from
  announce's swallow-all — the module author decides how to handle a failed push).
- **D4 — Testing.**
  - SDK unit (`atria_module_sdk/tests/`): `conn.invoke` + `requires_auth`;
    `params_model` schema + validation; `conn.block` env fill; `readiness` in health;
    `AtriaClient` push/update/remove/push_artifact (httpx `MockTransport`); manifest
    enrichment shape.
  - Host unit (`tests/`): `SkillToolContext.session_id/principal` wiring;
    `_make_handler` forwards `X-Atria-Session` + principal; `_run_stream` `block`
    event → `ctx.push_block`; `readiness=False` keeps a connector `PENDING`;
    `artifacts_remote` route auth (403 vs 200) + `ui_bridge.push_artifact`.
  - E2E (`OPENAI_API_KEY`, per CLAUDE.md): a module async job updates a live block via
    `AtriaClient.update_block`; a module pushes an artifact that appears in the
    conversation.

## Architecture / file structure

**SDK — created:** `atria_module_sdk/atria_module_sdk/client.py` (`AtriaClient`,
`AtriaClientError`); `atria_module_sdk/tests/` (new test suite).

**SDK — modified:** `connector.py` (`conn.block`, `conn.invoke`, `readiness_probe`,
`params_model` + `requires_auth` on `tool`, `expose_block`, manifest enrichment,
`X-Atria-Session` read, health `ready`); `cards.py` (unchanged — `block()` reused);
`__init__.py` (export `AtriaClient`, `AtriaClientError`).

**Host — created:** `atria/web/routes/artifacts_remote.py`.

**Host — modified:** `atria/core/skill_tools.py` (`SkillToolContext.session_id`,
`.principal`); `atria/web/ws_tool_broadcaster.py` (wire them); `atria/core/modules/remote.py`
(`_make_handler` forwards identity; `_run_stream` `block` event); `atria/core/modules/watcher.py`
(reconciler respects `health.ready`); `atria/web/ui_bridge.py` (`push_artifact`);
`atria/web/server.py` (register `artifacts_remote` router); `keycloak/realm-export.json`
(`module-push` for `atria-module`).

## Constraints

- SDK never imports `atria`. `AtriaClient` uses only `httpx` + env config.
- Reverse-push and artifact push require the `module-push` realm role; register/deregister
  keep `module-register`. `atria-module` holds both.
- `params_model` opt-in; hand-written `parameters=` unaffected.
- Identity forwarding is first-party trust (`{username, email}` + `session_id`), no token.
- No `Co-Authored-By: Claude` trailer. Test command `uv run --no-sync pytest`.
- `docs/` is gitignored — stage spec/plan with `git add -f`.

## Open follow-ups (not in this plan)

- MCP interop surface + MCP auto-registration (separate track).
- `AtriaClient` retry/backoff on transient push failures (start simple: single attempt + raise).
