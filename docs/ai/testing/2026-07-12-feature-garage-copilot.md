---
phase: testing
title: Testing Strategy — garage-copilot
description: Test scenarios derived from requirements success criteria and design components
---

# Testing Strategy

Feature: **garage-copilot**. Derived from requirements success criteria and design components.
Repo testing rule applies: unit tests via `uv run pytest` AND real end-to-end simulation with live
API calls — unit tests alone are not sufficient.

## Test Coverage Goals
- Unit coverage on all new/changed Python modules (tools, extractor, endpoints).
- Integration coverage of the agent↔tool↔store paths and both REST endpoints.
- One scripted end-to-end demo scenario (the success criterion itself) exercised against the real
  running web UI with real LLM calls.

## Unit Tests

### garage_copilot_query tool
- [x] Returns passages with citations for an in-corpus automotive query (unit: fake store carries
      chunk_id citations; live: demo question → cited [WSM-RR-2040#2] Vietnamese answer)
- [x] Returns explicit "no relevant passages" result for an out-of-corpus query (unit: zero hits →
      "Không tìm thấy" message, synthesize skipped; live: cake question → review notice, zero
      grounded claims — synthesis guardrails enforce citations, so no score floor needed)
- [x] Qdrant/embeddings unreachable → tool returns outage error, not fallback content
      (test_garage_copilot_agent_tool.py: timeout + nonzero-exit contracts)
- [x] Module discovered by the skill-tool loader via SKILL.md `tools:` frontmatter (D6 revised)
- [x] (new) garage.py CLI: dotenv parsing, parser args, garage collection/corpus defaults

### work_log_search tool
- [x] Paraphrased symptom query returns the matching stored WorkLogRecord (unit: fake store;
      live: EN paraphrase "vibration around 60 kph body shudder" → VI record demo240)
- [x] VIN/brand filters restrict results correctly (unit: VIN post-filter; brand rides the
      department filter; CLI flags pinned in tool cmd test)
- [x] Empty store → clean empty result (missing JSON records are skipped, no error)

### Work-log extractor
- [x] Full transcript → WorkLogRecord with every schema field populated (unit + live extract)
- [x] Rejected hypotheses (dead ends) captured with outcome `rejected` (live: "Mất cân bằng
      bánh xe → rejected")
- [x] Symptom preserved verbatim in original language (live: "Xe chạy khoảng 60km/h thì rung")
- [x] Abandoned session → record produced with status `incomplete` (unit: fallback +
      --incomplete flag; startup sweep descoped to tech debt)
- [x] Extraction output validates against the schema; malformed LLM output retried once, then
      schema-valid incomplete fallback (unit tests)

### Session anchoring
- [x] Session-create payload persists `ro_number`, `vin`, `brand` into session metadata
      (test_garage_session_anchoring.py + live Postgres round-trip via new conversations.meta
      JSON column — previously only title survived persistence)
- [x] Garage session-create rejects missing/empty `ro_number`/`vin`/`brand` (D3 layer 1:
      validate_garage_metadata → HTTP 422)
- [x] Metadata absent → no garage persona injected at all (build_garage_section returns "" for
      non-garage sessions — test_garage_prompt_section.py); in-conversation RO discipline lives
      in the section text for anchored sessions

## Integration Tests
- [ ] Agent turn with Vietnamese symptom → agent issues English `garage_copilot_query` call (D5 —
      LLM behaviour, validated in the Phase 4 real-API E2E)
- [ ] Agent answer containing manual content includes citation markers; answer from general
      knowledge includes the unverified-suggestion label (LLM behaviour → Phase 4 E2E)
- [x] Registry dispatch seam: skill-handler kwargs forwarding returns string output with citations
      (test_garage_agent_integration.py)
- [x] Garage corpus read denied by ProtectedPathGuard; denial message module-agnostic
      (test_garage_agent_integration.py)
- [x] Explicit close (POST /api/garage/worklogs/{id}/generate) triggers extractor; record saved
      + indexed (route test with CLI seam; live CLI extract verified)
- [x] `GET /api/garage/worklogs/{session_id}` returns the structured record (route test)
- [x] `GET /api/garage/worklogs/search?q=` returns results with filters (route test)
- [x] Transcript rendering excludes tool/system messages (route test — no raw tool output leaks
      into the extraction prompt)
- [x] RAG outage propagated as error tool-result, no silent fallback content
      (test_garage_agent_integration.py; in-chat wording is prompt-enforced → Phase 4 E2E)

## Frontend Tests (new)
- [x] splitCitations extracts [DOC#chunk] refs, ignores plain brackets (citations.test.ts, 6 tests)
- [x] isUnverifiedSuggestion detects the `⚠ Gợi ý chưa kiểm chứng` marker
- [x] tsc + full vitest suite green after MessageList/NewSessionModal changes (68 tests)
- [x] formatLatency/latencySummary — ms/s/min formatting, missing-metrics null (latency.test.ts,
      7 tests); full suite 74 passed (1 pre-existing npx-vitest/jsdom worker error on
      RemoteDashboard.test.tsx, unrelated)

## TTFT Metrics (2026-07-12)
- [x] First message_chunk of a run carries ttft_ms; later chunks don't (test_ttft_metrics.py, 4)
- [x] Unstamped query_started_at → chunks broadcast without the metric (no crash)
- [x] Empty assistant content does not consume the first-token stamp
- [x] Live E2E: `TTFT 4222ms session=249` logged; response line `ttft_ms=4222, total_ms=4240`
- [ ] Visual check of the `⚡ first token … · total …` footer in the browser (stakeholder
      walkthrough — bundle-grep confirms it shipped in `index-DFt7h_s5.js`)

## SSE Token Streaming (2026-07-12)
- [x] stream_json assembles content/tool_calls/usage from SSE and forwards deltas in order
      (test_streaming_llm.py, 12 tests)
- [x] stream flags set on payload (`stream`, `stream_options.include_usage`)
- [x] Mid-stream failure after emitted deltas → no model fallback (no double display)
- [x] Failure before any delta → fallback model tried
- [x] WebUICallback reconcile: duplicate final skipped; differing final retract+replace;
      withheld answer retracted; TTFT stamped on first streamed token
- [x] trimCodePoints trims by code points incl. astral chars (stream.test.ts, 4)
- [x] Live WS probe (session 249, real OpenAI): 171 message_chunk events over 8.0s, first at
      3.1s, 1 retract (completion-nudge path exercised live), verdict STREAMING
- [ ] Visual check in the browser: text renders progressively; nudge-path flash acceptable

## Tool-Phase Latency (2026-07-12)
- [x] build_query_cmd defaults hits-only; --synthesize opt-in (agent_tool tests updated)
- [x] build_reasoning_param: GPT-5/o-series get the param, others don't; "none" valid; invalid
      or unset → omitted (test_reasoning_effort.py, 4 tests)
- [x] Live constraint verified: gpt-5.4 + function tools + reasoning_effort low → HTTP 400;
      "none" accepted
- [x] Live demo turn (session 252): first text 2.8 s (pre-tool narration per prompt), tool
      3.6 s, total 14.0 s; composed answer carries [WSM-RR-2040#1]/[TSB-RR-2026-03#0] citations
      and the wheel-balance dead-end warning
- [ ] Completion-nudge retract/re-stream on tool-using turns — follow-up tuning candidate

## End-to-End Tests (live run 2026-07-12, real API, scratchpad/e2e_demo.py)
- [x] **Demo scenario (the success criterion)**: PASSED — session 241: RO-anchored create →
      "Xe chạy khoảng 60km/h thì rung" → cited guidance (WSM-RR-1005#1, WSM-RR-2041,
      TSB-RR-2026-03) → wheel balancing rejected, left CV axle confirmed → work log generated
      (symptom verbatim, dead end captured) → paraphrase search "Ghost bị rung nhẹ khoảng 60 cây
      số giờ" found it at score 0.833
- [x] **RO gate**: garage create without ro_number → HTTP 422 "A garage session requires a Repair
      Order anchor" (server-side; in-conversation refusal is prompt-enforced)
- [x] **Code-switching**: mixed VI/EN turns ("coast", "road test", "CV axle") handled naturally
      throughout the live conversation
- [ ] **Labeling under thin corpus**: not exercised live (all demo questions were in-corpus) —
      verify with an off-corpus question during the stakeholder walkthrough
- [x] Regression: full suite 326 passed; all 23 failures pre-existing (EK/connector drift,
      reproduced on main workspace) — zero garage-copilot regressions
- Latency (measured): agent turns 85/52/42 s; work-log extraction 7 s. Turn latency above the
  ~15 s aspiration — model/loop tuning follow-up. Language: two turn summaries + extracted
  root_cause came back English — extractor/persona prompt tuning follow-up.

## Test Data
- Mock RO/VIN/brand fixtures (e.g. RO-2026-0142, Rolls-Royce Ghost VIN)
- Sample automotive demo corpus under `modules/garage_copilot/sample_manuals/` (ingested via the
  enterprise_knowledge ingestion path with garage settings, own Qdrant collection)
- Canned transcript fixture for extractor unit tests (includes dead ends and code-switching)
- Pre-seeded work-log store for search tests

## Test Reporting & Coverage
- `make test-cov` for coverage report; new modules target full coverage, gaps justified in PR
- E2E demo run recorded (screen capture) as the stakeholder artifact

## Manual Testing
- Vietnamese conversation quality judged by a native speaker (fluency, code-switch handling)
- Citation vs. suggestion labels visually distinct in the web UI (light/dark)
- Work-log view readable by a non-technician (SM perspective)

## Performance Testing
- Tool-augmented turn latency < ~15 s; extraction < 60 s (demo tolerances, measured once)

## Bug Tracking
- Issues tracked in the feature branch PR; regressions get a pytest case before fix (repo TDD norm)
