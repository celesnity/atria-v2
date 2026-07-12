---
phase: implementation
title: Implementation Guide — garage-copilot
description: Running implementation log — changed files, decisions, deviations, edge cases
---

# Implementation Guide

Feature: **garage-copilot**. Worktree: `.worktrees/feature-garage-copilot`, branch
`feature-garage-copilot`. Plan: `docs/ai/planning/2026-07-12-feature-garage-copilot.md`.

## Development Setup
**How do we get started?**

- `uv sync --extra dev` (plain `uv sync` skips pytest — `uv run pytest` then silently uses the
  global Homebrew pytest and every import fails); then
  `uv pip install -r modules/enterprise_knowledge/requirements.txt` (openai, qdrant-client, …)
- `OPENAI_API_KEY` required for embeddings/synthesis and all E2E testing (repo rule)
- Qdrant running locally (add to docker services alongside db/redis; do NOT build the Atria
  docker image locally — it OOMs; run Atria natively)
- `npx ai-devkit@latest lint --feature garage-copilot` must stay green

## Code Structure
**How is the code organized?**

- `modules/garage_copilot/` — new code-bearing skill module (SKILL.md with `tools:` frontmatter,
  `agent_tools.py`, garage settings, `sample_manuals/` corpus) reusing
  `modules/enterprise_knowledge/scripts/` as a retrieval library (design D6 revised)
- `atria/core/agents/prompts/templates/system/main/main-garage-copilot.md` — prompt section
- `atria/web/` — session-create extension (RO/VIN/brand), work-log endpoints
- Work-log store under `ATRIA_DIR` (never committed)

## Implementation Notes
**Key technical details to remember:**

### Task 1.1 — maintenance_copilot audit (DONE 2026-07-12; outcome differs from plan)

Finding: `modules/maintenance_copilot/` is a tombstone. The team deprecated the module
(`3950a51 "deprecated module prepare to transform"`) and deleted the pipeline
(`6889b8b "remove unused copilot module"` — removed copilot.py 623 lines, chunking, corpus,
extraction, answer_schema/validation, audit, budget, client, config, backend app). The runtime
service moved to the cloud: `atria/web/routes/maintenance.py` proxies via `RemoteConnector` built
from a module manifest that is absent locally. In-process module `tools.py` files were retired in
favor of remote proxy specs on collision (`registry.py`).

Replacement identified: `modules/enterprise_knowledge` is the in-repo transformation of the same
stack — `scripts/` has chunking, bm25, index_store (Qdrant), corpus, extraction, synthesis,
guardrails, audit, budget, identity/acl, graph_* (GraphRAG), evaluate; `agent_tools.py` exposes a
typed `enterprise_knowledge_query` tool registered via SKILL.md `tools:` frontmatter and the
module-aware skill-tool loader; answers are cited and in Vietnamese. Config
(`scripts/config.py`) maps roles (index_embed, synthesis, kg_extract) to OpenAI-compatible
endpoints, overridable via `EK_<ROLE>_<FIELD>` env vars; embeddings default
text-embedding-3-small.

Decisions recorded: design D6 revised (build `modules/garage_copilot/` reusing
enterprise_knowledge scripts as a library; own corpus dir + Qdrant collection; fixed open-access
identity; fallback = copy trimmed scripts), D8 updated accordingly. New task 1.1b (scaffold)
added to planning; new risks: enterprise_knowledge coupling, Qdrant infra dependency.

Changed files: `.gitignore` (replaced `docs/` ignore with `docs/*` + `!docs/ai/` so the ai-devkit
feature docs are tracked on the branch — flagged to the team; also `.worktrees/` ignored, added
at worktree setup). Removed the useless tombstone copy from the worktree
(`modules/maintenance_copilot/` — contained only `.deps.sha256` + a stale `.pyc`).

Edge case noted: gitignore cannot re-include under an excluded parent dir — `!docs/ai/` only
works with `docs/*`, not `docs/`.

### Task 1.1b — modules/garage_copilot scaffold (DONE 2026-07-12)

Changed files: `modules/garage_copilot/{SKILL.md, agent_tools.py, scripts/garage.py}`,
`tests/test_garage_copilot_agent_tool.py` (12 tests, written first — TDD).

- `agent_tools.py` mirrors enterprise_knowledge's tool contract exactly: pure `build_query_cmd`
  (absolute script path), handler returns `{"success", "output": <raw JSON string>, "error"}` —
  output MUST be a string (react-loop compactor contract), timeout/nonzero-exit surface as
  outages with `output: None`. No `user_id` param — garage v1 is open-access.
- `scripts/garage.py` reuses EK scripts in-process via EK's own `_bootstrap.sibling()`
  (collision-proof file-location imports). Garage-specific: collection `garage_chunks`
  (`GARAGE_QDRANT_COLLECTION`), corpus `sample_manuals/` (`GARAGE_CORPUS_DIR`), open access
  (`acl_filter=None`), own audit log (`data/audit.log.jsonl` — EK's `append_event` takes a path),
  no GraphRAG/neo4j. Health = index_embed + synthesis + qdrant probes.
- Deviation (per D6 fallback): `_parse_dotenv`/`_load_dotenv` copied from knowledge.py rather than
  imported — knowledge.py's `from _bootstrap import sibling` needs EK's dir on sys.path, so it
  isn't cleanly importable in-process. Walk-up `.env` search still finds the main workspace `.env`
  from inside the worktree.
- Environment gotchas (both now in Development Setup): plain `uv sync` skips dev extras → `uv run
  pytest` silently falls through to Homebrew's global pytest (No module named 'atria'); use
  `uv sync --extra dev` or `make install`. EK module deps (`openai`, `qdrant-client`, `chonkie`,
  `openpyxl`, `neo4j`) live in `modules/enterprise_knowledge/requirements.txt`, not pyproject —
  `uv pip install -r` them.
- Validation: 18 tests green (12 garage + 6 EK regression); live `garage.py health` all ok
  (Qdrant was already running in docker as `atria-v2-qdrant-1`); black/ruff clean; mypy clean on
  new files (3 pre-existing errors in atria core, reproduced on main workspace).

### Tasks 1.2 + 1.3 — corpus + query tool (DONE 2026-07-12)

Changed files: `modules/garage_copilot/sample_manuals/*.md` (5 authored manual excerpts),
`modules/garage_copilot/.gitignore` (ignores runtime `data/`, mirrors vetc_copilot),
`tests/test_garage_copilot_agent_tool.py` (now 15 tests).

- Corpus deliberately deep on the demo scenario and internally cross-referenced (road test →
  diagnosis stages → CV axle R&I → TSB), so multi-hop questions retrieve coherently. English
  content (citations stay in manual language); frontmatter per EK corpus contract
  (`doc_id/title/department/classification`), department `GARAGE`.
- Ingest: 5 documents → 25 chunks in `garage_chunks` (EK chunking via chonkie, local).
- Live validation: demo question ("vibrates ~60 km/h, worse under light acceleration, eases
  coasting") → hybrid retrieval ranks WSM-RR-1005/TSB-RR-2026-03/WSM-RR-2040 top; synthesized
  Vietnamese answer cites [WSM-RR-2040#2] naming the inner CV joint.
- Edge case discovered: hybrid RRF always returns hits, even for out-of-corpus questions
  (~0.55 scores for a cake question). No score floor added — EK's synthesis guardrails already
  enforce citation grounding (`enforce_citations` drops uncited sentences; low-confidence →
  Vietnamese review notice, `needs_review: true`). Validated live: cake question → zero grounded
  claims, review notice. The agent prompt layer (Task 1.5, D7 labels) is the second defence.
- Unit tests use an injected fake store (garage.py's `store=` params exist for this), so the
  suite is hermetic — no Qdrant/API needed.

### Task 1.4 — session anchoring, backend (DONE 2026-07-12; frontend form → Task 2.2)

Changed files: `atria/db/models.py` (Conversation.meta JSON column), `atria/db/connection.py`
(idempotent `ALTER TABLE conversations ADD COLUMN IF NOT EXISTS meta JSON` in init_schema —
same pattern as the existing messages.role widening), `atria/db/repositories/conversation_repo.py`
(create/update accept `meta`), `atria/core/context_engineering/history/session_manager/
pg_manager.py` (create_session takes `metadata`; `merge_row_metadata` rebuilds Session.metadata
on load with the title column authoritative; save_session persists metadata sans title),
`atria/web/routes/sessions.py` (CreateSessionRequest.metadata, `validate_garage_metadata` → 422,
metadata-carrying requests skip empty-session reuse), `tests/test_garage_session_anchoring.py`.

- Root gap fixed: pg_manager previously persisted ONLY `title` from Session.metadata — everything
  else silently vanished on reload. Garage anchoring forced the fix; it benefits any future
  metadata user. (A model comment on ChannelSession documents the team's create_all-won't-ALTER
  caveat — the idempotent ALTER handles exactly that.)
- Design D3 layer 1 enforced server-side (422), not just in the future form: session_type garage
  without non-blank ro_number/vin/brand cannot exist regardless of client.
- Validation: 7 unit tests green; live round-trip against the running Postgres (localhost:5433)
  including init_schema ALTER — created garage session, force-saved, fresh-manager load, all
  fields intact, soft-deleted after. 25-test regression subset green. Only PgSessionManager
  implements the interface (checked), so the new kwarg breaks no other implementation.

### Task 1.5 — garage-copilot prompt section (DONE 2026-07-12)

Changed files: `atria/core/agents/prompts/templates/system/main/main-garage-copilot.md`,
`atria/core/agents/prompts/garage.py` (build_garage_section), `atria/web/agent_executor.py`
(injection next to persona/workspace blocks), `tests/test_garage_prompt_section.py` (5 tests).

- DESIGN DEVIATION (recorded): the design said "via PromptComposer conditioned on a garage
  session flag", but the composer runs inside the session-agnostic agent — session-conditioned
  content (persona, workspace, module skills) is injected by the web agent executor. The garage
  section follows that existing pattern instead: `build_garage_section(session.metadata)` is
  pure/testable and appended in `_run_agent_sync`, wrapped so a failure can never break a turn.
- Section content: vibe-repairing persona; Vietnamese-first with code-switching; query
  `garage_copilot_query` in English; D7 conventions (inline citations, `⚠ Gợi ý chưa kiểm chứng`
  blockquote); RO discipline (one session = one RO/vehicle; Dự Toán Phát Sinh drafted but never
  approved by the copilot); conversation-is-the-work-log guidance (state dead ends explicitly,
  confirm root cause before close; `work_log_search` when a symptom sounds familiar — tool ships
  in Phase 3). Prose only; a unit test enforces the template stays table-free (repo rule).
- Dynamic anchor block appends the session's actual RO/VIN/brand/technician values.

Phase 1 / Milestone M1 complete: 34-test sweep green (garage suites + EK + web regressions),
ai-devkit lint green. 13 files changed/untracked on the branch, uncommitted pending user's call.

### Phase 2 — Tasks 2.1 + 2.2 + 2.3 (DONE 2026-07-12)

Changed files: `tests/test_garage_agent_integration.py`, `atria/models/config.py` (denial message
generalized), `web-ui/src/utils/citations.ts` + `.test.ts`, `web-ui/src/components/Chat/
MessageList.tsx` (blockquote renderer + citation badges in p/li), `web-ui/src/components/Layout/
NewSessionModal.tsx` (garage toggle + RO/VIN/brand/technician fields), `web-ui/src/api/client.ts`
(createSession metadata param), `atria/web/static/*` (rebuilt via make build-ui).

- 2.1/2.3 offline scope: the react loop reaches skill tools via
  `ToolRegistry._make_skill_handler` (kwargs forwarding) — pinned with tests including the
  outage shape (success=false, output=None). VI→EN and citation display are LLM behaviours →
  Phase 4 real-API E2E.
- Discovery: the default protected-path glob `modules/*/sample_manuals` already covers the garage
  corpus (no config needed); the denial message named the retired `maintenance_copilot_query`
  tool, now generalized to "the owning module's query tool". Nothing pinned the old text.
- D7 rendering: `splitCitations` (regex `\[([A-Z]{2,}[A-Z0-9-]*#\d+)\]` — matches WSM-RR-2040#2,
  DOC002#0; ignores array[0]/[note]) → badge spans; blockquotes starting with
  `⚠ Gợi ý chưa kiểm chứng` → amber callout (no `semantic-warning` token exists in the Tailwind
  theme; amber-500 scale is the app's accent, works in both theme scopes).
- Garage session form: checkbox toggle reveals the four fields; create button disabled while
  RO/VIN/brand blank ("no RO, no repair session" hint) — client-side layer over the 422.

### Phase 3 — work log & search (DONE 2026-07-12)

Changed files: `modules/garage_copilot/scripts/worklog.py` (schema/extract/store/index/search
CLI), `modules/garage_copilot/agent_tools.py` (+`work_log_search` ToolSpec),
`atria/web/routes/garage.py` (generate/get/search endpoints), `atria/web/routes/__init__.py` +
`atria/web/server.py` (router wiring), `tests/test_garage_worklog.py` (9),
`tests/test_garage_worklog_routes.py` (5).

- The conversation→work-log extraction is Vietnamese-prompted, schema-validated (plain-dict
  validator, no new deps), retried once, with a schema-valid `incomplete` fallback so a session
  can never end log-less. Anchor fields (session/RO/VIN/brand/technician) are stamped from
  session metadata — never trusted from the LLM.
- Work logs get their own Qdrant collection (`garage_worklogs`); the embedded text is
  symptom+cause+fix+hypotheses (what the next KTV would search). Brand rides IndexStore's
  department filter; VIN filters post-retrieval via the JSON store; missing JSON → hit skipped.
- REST: generate IS the explicit close action (assumption recorded in requirements). Routes shell
  out to worklog.py (one store implementation; no in-process pipeline import — same discipline
  as the maintenance route). Transcript rendering includes only user/assistant turns.
- Live validation (real LLM + Qdrant): realistic 8-turn demo transcript → complete record with
  verbatim symptom, rejected-hypothesis dead end, real part number, 5 citations; English
  paraphrase search ("vibration around 60 kph body shudder") retrieved the Vietnamese record.
- 53-test sweep green; mypy clean on new files; server import smoke ok.

### Phase 4 — live E2E demo (DONE 2026-07-12)

The full success-criterion scenario ran live against a natively-hosted worktree server
(port 8081; docker db/redis/qdrant; env per start-local.sh pattern). Driver:
`scratchpad/e2e_demo.py`. All 8 steps passed — see the testing doc for the transcript summary.

Environment fixes discovered:
- AUTH_MODE=none synthesizes user id 0 but no `users` row 0 exists → 500 on any
  workspace-provisioning endpoint (FK violation). Fix (idempotent): INSERT users row id 0
  ('local@localhost'). Applies to any fresh DB used with AUTH_MODE=none.
- The worktree needs `.env` copied from the main workspace (gitignored, doesn't carry over).

Findings for follow-up (not blockers):
- Turn latency 42–85 s (multi-tool ReAct loop through OpenRouter-configured model) vs the ~15 s
  aspiration; work-log extraction 7 s (target met).
- Language drift: assistant turn SUMMARIES (react-loop final summaries) and the extracted
  root_cause came back in English while conversation content held Vietnamese. Candidates: extend
  the persona rule to summaries; harden the extractor prompt ("mọi trường bằng tiếng Việt").
- Thin-corpus labeling behaviour not exercised live (demo questions were all in-corpus).

### Demo seed data + guide (DONE 2026-07-12)

Changed files: `modules/garage_copilot/scripts/seed_demo.py` (idempotent seeder: corpus ingest +
5 historical work logs across all 3 brands), `modules/garage_copilot/sample_manuals/
WSM-LAM-3020_urus_battery_drain.md` (6th corpus doc — brand variety),
`modules/garage_copilot/DEMO.md` (stakeholder demo walkthrough: setup, cast, 3 use cases with
exact Vietnamese messages and expected outcomes, cheat sheet), `tests/test_garage_seed.py` (3),
`main-garage-copilot.md` (prompt hardening, below), ingest-count test made corpus-size-agnostic.

- Seed work logs: the 60 km/h CV-joint case (with the wheel-balance dead end on record — the
  flywheel hit for the star scenario), brake-judder DTV, Urus dashcam battery drain, McLaren
  outer-joint click, centre-bearing drone. All schema-validated by test; all searchable live.
- **Prompt hardening from live validation**: asked "xưởng mình gặp ca nào giống vậy chưa?", the
  copilot originally answered from the TSB in the corpus (manufacturer history) WITHOUT calling
  `work_log_search`. Rule added: workshop-history questions call work_log_search FIRST and cite
  the past case's RO. Re-validated live: reply now cites both matching past cases by RO number
  (RO-2026-0177 + seeded RO-2026-0101) with root cause and fix, 30 s.
- Observation (recorded): the PERSISTED assistant message content is sometimes the react-loop's
  final summary rather than the streamed reply the UI shows — REST-level content checks can
  false-negative on things like the ⚠ label. UI walkthrough remains the source of truth for
  display-level expectations.

### Fix: garage UI was on a dead component (2026-07-12, user-reported)

User report: "New chat" showed no garage checkbox. Root cause: Task 2.2 put the garage fields in
`NewSessionModal`/`SessionsSidebar` — which **nothing imports** (dead legacy code; the bundle
didn't even contain the pre-existing "Select Workspace" strings). The live path is: sidebar
"New chat" → `createConversation` → `POST /api/projects/{id}/conversations` →
`ProjectService.create_conversation` → `create_session`.

Fix (all layers of the LIVE path):
- `CreateConversationRequest.metadata` + garage validation (422) in `routes/projects.py`;
  `ProjectService.create_conversation(metadata=...)` threads to `create_session` (2 new tests).
- Reverted the garage block from the dead `NewSessionModal` (left as it was).
- New `web-ui/src/components/Layout/GarageSessionModal.tsx` (RO/VIN/brand/technician, disabled
  until valid); amber "Garage repair session" button with wrench icon added under the New chat
  CTA in `ProjectSidebar`; `apiClient.createConversation` + projects store accept metadata;
  conversation named "RO-xxxx · Brand". Static rebuilt; server restarted.
- Live-verified: 422 without RO through the conversations endpoint; full garage conversation
  247 created with metadata persisted in `conversations.meta`.
- Lesson recorded: verify a UI change is on the RENDERED component tree, not just a component
  that compiles — dead code compiles fine. The bundle-grep check (`grep "Garage repair session"
  static/assets/*.js`) is the cheap guard.

### Provider switch OpenRouter → OpenAI (2026-07-12, user-requested)

User set `OPENAI_API_KEY` and pointed `ATRIA_API_BASE_URL` at OpenAI. Two corrections were
needed: the agent POSTs `api_base_url` verbatim (`configuration.py:100`), so it must carry the
full `/chat/completions` path; and `SEARCH_EMBED_MODEL` needed the bare OpenAI name
(`text-embedding-3-small`, no `openai/` prefix — OpenAI rejects it). Synced three config
surfaces: main `.env`, worktree `.env` (server runs from the worktree; copies don't auto-sync),
`~/.atria/settings.json`. Model `gpt-5.4-mini` verified live; RAG + agent chat E2E pass; turn
latency dropped to ~25 s.

### TTFT latency metrics (2026-07-12, user-requested)

Time-to-first-token measured at both ends, from query submission:
- Backend: `AgentExecutor.execute_query` stamps `query_started_at` (monotonic) at query arrival
  and threads it into `WebUICallback`; the first `on_assistant_message` of the run computes
  `first_token_ms`, logs `TTFT ...ms session=...`, and carries `ttft_ms` in that chunk's WS
  payload. `_run_agent_sync` returns `ttft_ms`; the response log line adds `ttft_ms`/`total_ms`.
- Frontend (perceived, displayed): `turnTimingBySession` in `stores/chat.ts` — stamped in
  `sendMessage` (or at `message_start` for turns this client didn't initiate, e.g. queued
  injections), TTFT captured on the first `message_chunk`, and on `message_complete` the
  metrics (`ttftMs`, `totalMs`, `serverTtftMs`) are attached to the turn's assistant bubble.
  `MessageList` renders a muted footer: `⚡ first token 4.2s · total 27s` (formatting in
  `utils/latency.ts`).
- Metrics are ephemeral (not persisted with the session) — history reloads show no footer.
- Tests: `tests/test_ttft_metrics.py` (4 — first-chunk-only ttft, no-stamp, empty-content) and
  `web-ui/src/utils/latency.test.ts` (7). Live E2E: `TTFT 4222ms session=249`,
  `ttft_ms=4222, total_ms=4240` in the server log.

### True SSE token streaming (2026-07-12, user-reported via /structured-debug)

User report: the final response block renders all at once — the user waits for the whole LLM
generation. Root cause (evidence-first): streaming never existed anywhere in the stack —
`AgentHttpClient.post_json` is a blocking POST (no `stream: true` in the repo), the callback
interface had no token-level hook, and the executor broadcasts each ReAct message whole via
`on_assistant_message`. The TTFT metric proved it: first token 4222ms ≈ total 4240ms.

Fix (approved option A — true streaming):
- `AgentHttpClient.stream_json`: SSE mode (`stream: true` + `stream_options.include_usage`),
  forwards `delta.content` per chunk, assembles the body in non-streaming shape (content,
  tool_calls accumulated by index, reasoning_content, usage). Retries 429/503/network only
  before the first delta reaches the UI; mid-stream failures are terminal (`emitted` guard,
  mutably shared so a mid-read exception can't reset the count and double-emit).
- `call_llm(on_content_delta=)`: streams when the client supports it; model-fallback is refused
  once deltas were emitted (would display the text twice). Shared `_build_llm_result` parses
  both paths.
- Executor: passes `ui_callback.on_assistant_token` when `wants_stream_tokens` (web only; TUI
  and subagents unchanged). The completion-nudge withheld path calls `on_assistant_retract`.
- `WebUICallback` reconciles streaming with display decisions: identical (stripped) final
  content → duplicate skipped; differing content (cleaner edits, task_complete summary) →
  `message_retract` (trim in code points) then the authoritative chunk; withheld → retract.
  TTFT now stamps on the first streamed token.
- Frontend: `message_retract` handler trims the active turn's bubble via `trimCodePoints`
  (`utils/stream.ts` — code points, matching Python `len`). Chunk pipeline itself unchanged.
- Known cosmetic behavior: when the completion nudge fires, the withheld answer streams, is
  retracted, and the final answer re-streams — a visible flash, by design (rare path).
- Tests: `tests/test_streaming_llm.py` (12 — SSE assembly, tool-call accumulation, payload
  flags, error paths, fallback guard, reconcile/retract/TTFT), `web-ui/src/utils/stream.test.ts`
  (4). Live WS probe: **171 chunks over 8.0s, first token at 3.1s** (was: 1 chunk, first ≈
  total); server log `ttft_ms=3079, total_ms=7981`.

### TTFT 18s → 2.8s: tool-phase latency fixes (2026-07-12, user-reported)

Streaming fixed rendering, but TTFT on real garage turns was still ~18.6 s because the turn sat
inside silent phases: LLM call #1 emitting only a tool call (~4 s), `garage_copilot_query` at
~14 s, LLM call #2 reasoning (~2 s). Measured: retrieval itself is 2.65 s — the rest of the tool
time was the synthesis pass, a full gpt-4o-mini generation the main agent then re-wrote anyway
(two generations per turn, one visible). Three approved fixes:

- **A — hits-only tool path**: `garage_copilot_query` now defaults `synthesize=False` (schema no
  longer exposes it; CLI keeps `--synthesize` for humans/API). The agent composes the streamed
  Vietnamese answer from raw hits, citing each hit's `chunk_id`. Persona prompt updated
  accordingly. Tool time 14 s → 3.6 s live.
- **B — narrate before slow tools** (persona prompt): one short Vietnamese line before a lookup
  ("Để em tra WSM về rung ở dải 60 km/h…") — streams at ~3 s, so the wait reads as attended.
- **C — `reasoning_effort` knob**: `AppConfig.reasoning_effort` + `ATRIA_REASONING_EFFORT` env
  override, applied via `build_reasoning_param` (GPT-5 family/o-series only). **Live-discovered
  API constraint**: on /v1/chat/completions, gpt-5.4 rejects function tools with any effort
  except `"none"` (400: "use /v1/responses or set reasoning_effort to 'none'") — so the value is
  `none`, which also maximizes the latency win.

Re-measured on the demo's exact turn (session 252): **first text 2.8 s** (narration line), tool
3.6 s, cited answer streams from ~7 s, **total 14.0 s** (was 18.6 s / 37 s). Citations and the
wheel-balance dead-end warning verified intact in the composed answer.

Known follow-up: the completion nudge now visibly retracts + re-streams the answer on
tool-using turns (~4 s extra + a flash) — consider skipping the nudge when the turn already
produced a substantive cited answer. Core-agent behavior; not changed unilaterally.

## Technical Debt & TODOs
- Decide with the team whether `docs/*` + `!docs/ai/` should merge to main or stay branch-local.
- `modules/maintenance_copilot/.deps.sha256` still sits untracked in the main workspace — not our
  branch's concern, but worth a cleanup note to the team.
- D9 startup sweep for abandoned garage sessions descoped from v1 demo (explicit generate covers
  it; `worklog.py extract --incomplete` is ready for the sweep to call).
- Web UI: work-log view page + a "Close & generate work log" button (the REST endpoints exist;
  demo can drive them directly). Candidate Phase 4 polish.
- The garage prompt references `work_log_search` — tool now ships, reference is live.
