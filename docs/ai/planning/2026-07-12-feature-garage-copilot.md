---
phase: planning
title: Project Planning & Task Breakdown — garage-copilot
description: Ordered implementation plan derived from requirements, design, and testing docs
---

# Project Planning & Task Breakdown

Feature: **garage-copilot**. Derived from `docs/ai/requirements|design|testing/2026-07-12-feature-garage-copilot.md`.
Task IDs reference design decisions (D1–D6) and testing scenarios (T:).

## Milestones
**What are the major checkpoints?**

- [x] M1 — Foundation: corpus queryable, session anchored to RO+VIN, copilot persona live
      (DONE 2026-07-12 — backend scope; garage session-create UI fields land with Task 2.2)
- [x] M2 — Core loop plumbing complete 2026-07-12 (dispatch seams, UI rendering, outage path);
      the live cited-conversation proof rides the Phase 4 real-API demo
- [x] M3 — Work log: DONE 2026-07-12 — generate endpoint produces the structured record; live
      extract + English-paraphrase search over a Vietnamese record verified (flywheel closed)
- [x] M4 — Demo: DONE 2026-07-12 — scripted success-criterion scenario PASSED live end-to-end
      (all 8 steps); server browsable at :8081 for the visual walkthrough

## Task Breakdown
**What specific work needs to be done?**

### Phase 1: Foundation (M1)
- [x] Task 1.1 — DONE 2026-07-12 (outcome differs from plan): audit found
      `modules/maintenance_copilot` is a tombstone — pipeline deleted (3950a51, 6889b8b), service
      moved to cloud. Nothing to vendor. Replacement identified: `modules/enterprise_knowledge`
      retrieval stack (design D6 revised). New scaffold task 1.1b added; Qdrant infra risk added.
- [x] Task 1.1b — DONE 2026-07-12: `modules/garage_copilot/` scaffolded (SKILL.md with `tools:`
      frontmatter, agent_tools.py with `garage_copilot_query`, scripts/garage.py CLI reusing EK
      scripts via its `_bootstrap.sibling` loader; own collection `garage_chunks`, open access).
      Validated: 12 unit tests green (incl. loader discovery, outage contracts); live
      `garage.py health` → index_embed/synthesis/qdrant all ok. Note: EK module deps
      (`openai`, `qdrant-client`, …) come from `modules/enterprise_knowledge/requirements.txt`,
      not the main pyproject — install into the venv as a setup step.
- [x] Task 1.2 — DONE 2026-07-12: 5 manual excerpts authored (WSM-RR-1005 road test, WSM-RR-2040
      driveline vibration diagnosis, WSM-RR-2041 CV axle R&I with torques/parts, WSM-RR-2010 wheel
      balancing, TSB-RR-2026-03 Ghost II 55–70 km/h known issue) → 25 chunks indexed in
      `garage_chunks`. Validated live: demo question returns cited Vietnamese answer
      ([WSM-RR-2040#2] → inner CV joint); out-of-corpus question triggers the synthesis
      guardrails (review notice, zero grounded claims — no fabricated citations).
- [x] Task 1.3 — DONE 2026-07-12 (implemented during 1.1b): `garage_copilot_query` in
      agent_tools.py, discovered via SKILL.md frontmatter + skill-tool loader. 15 unit tests
      green (command building, string-output contract, outage surfacing, in/out-of-corpus via
      fake store, ingest counts).
- [x] Task 1.4 — DONE 2026-07-12 (backend scope; frontend form split to Task 2.2): session-create
      accepts optional `metadata`; `session_type: garage` requires non-blank ro_number/vin/brand
      (422 otherwise); metadata now round-trips through a new `conversations.meta` JSON column
      (model + idempotent ALTER in init_schema + repo + pg_manager). Metadata-carrying sessions
      skip empty-session reuse. Validated: 7 unit tests + live Postgres round-trip
      (create → save → fresh load → all garage fields intact).
- [x] Task 1.5 — DONE 2026-07-12 (deviation: injected by the web agent executor per-session, NOT
      via PromptComposer — the composer never sees session context; persona/workspace blocks are
      injected at the same point). `main-garage-copilot.md` (persona, Vietnamese-first +
      code-switching, D7 citation/label convention with `⚠ Gợi ý chưa kiểm chứng`, RO discipline
      incl. Dự Toán Phát Sinh boundary, conversation-is-the-work-log guidance) +
      `atria/core/agents/prompts/garage.py` `build_garage_section` appending the live RO/VIN/
      brand/technician anchor block. Prose only, no tables. 5 unit tests: values present, label
      conventions present, non-garage sessions get empty string (no leak), template table-free.

### Phase 2: Core diagnosis loop (M2)
- [x] Task 2.1 — DONE 2026-07-12 (offline scope): registry dispatch seam pinned
      (ToolRegistry._make_skill_handler kwargs forwarding → string output with citations);
      VI→EN query formulation and citation display are LLM behaviours — validated in the Phase 4
      real-API E2E. Bonus: garage corpus confirmed protected by the modules/*/sample_manuals
      guard glob; the denial message generalized (it named the retired maintenance_copilot_query).
- [x] Task 2.2 — DONE 2026-07-12: MessageList renders [DOC#chunk] citation refs as badges and
      `⚠ Gợi ý chưa kiểm chứng` blockquotes as amber warning callouts (pure helpers in
      utils/citations.ts, 6 vitest tests); NewSessionModal gains a "Garage repair session"
      toggle with RO/VIN/brand/technician fields (create disabled until required fields filled);
      apiClient.createSession passes metadata. tsc clean, 68 frontend tests green,
      `make build-ui` rebuilt static. Visual check rides the Phase 4 live demo.
- [x] Task 2.3 — DONE 2026-07-12: outage surfaces as an error tool-result (success=false,
      output=None) through the registry calling convention — never content the model could
      silently repeat; integration test pins it.

### Phase 3: Work log & search (M3)
- [x] Task 3.1 — DONE 2026-07-12: `modules/garage_copilot/scripts/worklog.py` — WorkLogRecord
      schema validation + JSON store (GARAGE_WORKLOG_DIR → $ATRIA_DIR/garage/worklogs → module
      data/) + embedding index in own Qdrant collection `garage_worklogs` (EK stack reuse; brand
      rides the department filter). Round-trip unit tests green.
- [x] Task 3.2 — DONE 2026-07-12: `worklog.py extract` — Vietnamese schema-constrained LLM
      extraction, anchor fields stamped from the session (never trusted from the LLM), one retry
      on invalid output, schema-valid `incomplete` fallback so a session always gets a log.
      Live-validated on a realistic transcript: symptom verbatim, dead end captured
      (wheel imbalance → rejected), real part number, 5 citations.
- [x] Task 3.3 — DONE 2026-07-12: `work_log_search` ToolSpec in agent_tools.py + `worklog.py
      search` (hybrid paraphrase retrieval; VIN post-filter via JSON store, brand via department
      filter). Live-validated: English paraphrase query found the Vietnamese record.
- [x] Task 3.4 — DONE 2026-07-12 (endpoints; UI view deferred to Phase 4 polish): new
      `atria/web/routes/garage.py` — POST /api/garage/worklogs/{id}/generate,
      GET /api/garage/worklogs/{id}, GET /api/garage/worklogs/search; registered in server.
      Route tests with monkeypatched seams (maintenance-route style).
- [x] Task 3.5 — DONE 2026-07-12 (revised semantics): the generate endpoint IS the explicit
      close action (requirements assumption); `--incomplete` flag supported for sweeps.
      DEVIATION: the D9 startup sweep for abandoned sessions is descoped to tech debt for the
      demo — explicit generate covers the demo path.

### Phase 4: Demo hardening (M4)
- [x] Task 4.1 — DONE 2026-07-12: fixtures exist across the test suite (mock RO/VIN metadata,
      demo corpus, canned transcript, pre-seeded work-log records in unit tests).
- [x] Task 4.2 — DONE 2026-07-12: scripted E2E with real API calls PASSED all steps against the
      running server (port 8081): RO-gate 422 → anchored session → 3 Vietnamese turns with
      corpus citations (WSM-RR-1005/2041, TSB-RR-2026-03) converging wheel-balance→CV-axle →
      work log generated in 7 s (symptom verbatim, dead end captured, 3 citations) → Vietnamese
      paraphrase search found the session at score 0.833. Driver: scratchpad/e2e_demo.py.
- [~] Task 4.3 — Latency measured: agent turns 42–85 s (multi-tool ReAct loop; above the ~15 s
      aspiration — model/loop tuning is follow-up work); extraction 7 s (< 60 s target met).
      Vietnamese quality: mostly held, but two turn SUMMARIES and the extracted root_cause came
      back in English — prompt-tuning follow-up. Native-speaker review pending (stakeholder).
- [x] Task 4.4 — DONE 2026-07-12: black/ruff/mypy clean on all changed files; full suite 326
      passed with ZERO garage regressions (23 failures are pre-existing EK/connector drift,
      reproduced identically on the main workspace — unmasked here because installing EK module
      requirements activated previously-skipped tests). The E2E driver output is the demo record.

### Post-M4: Demo enablement (added 2026-07-12, stakeholder request)
- [x] Seed data — `scripts/seed_demo.py`: 6-doc corpus ingest + 5 historical work logs
      (all brands, incl. the star-scenario flywheel case). Idempotent; schema-tested; verified
      searchable live via REST and in-conversation.
- [x] `modules/garage_copilot/DEMO.md` — stakeholder demo guide: setup, cast, 3 scripted use
      cases (star scenario, flywheel, trust boundaries) with exact Vietnamese messages and
      expected outcomes, cheat sheet + troubleshooting. Both headline promises live-validated;
      prompt hardened so workshop-history questions reliably use work_log_search.

## Dependencies
**What needs to happen in what order?**

- 1.1 → 1.2 → 1.3 (pipeline before corpus before tool); 1.4 → 1.5 (metadata before prompt gate).
- Phase 2 needs 1.3 + 1.5. Phase 3 is parallelizable with Phase 2 except 3.5 (needs sessions
  flowing) and agent use of 3.3 (needs 2.1).
- 4.2 needs everything; OPENAI_API_KEY required for all E2E work (repo rule).
- External: none beyond LLM API access; no SAP, no OEM licensing in v1.

## Timeline & Estimates
**When will things be done?**

- Phase 1: ~2–3 days (corpus creation 1.2 is the swing item)
- Phase 2: ~1–2 days · Phase 3: ~2–3 days · Phase 4: ~1 day
- Buffer: +2 days for VI→EN retrieval quality iteration (design D5 fallback: bilingual query
  expansion) and extractor prompt tuning.

## Risks & Mitigation
**What could go wrong?**

- **Corpus availability (1.2)** — no ready automotive manuals. Mitigation: author sample manuals
  mirroring `sample_manuals/` structure, scoped tightly to the demo scenario domain.
- **VI→EN retrieval quality** — translated queries may miss. Mitigation: bilingual query expansion
  inside the tool (D5 fallback); covered by integration test before demo.
- **Extractor fidelity** — hallucinated log fields would poison the flywheel. Mitigation:
  schema-constrained output + verbatim-symptom test + human review of demo logs.
- ~~maintenance_copilot coupling~~ — RESOLVED 2026-07-12: module was deleted from the repo; design
  pivoted to reusing `modules/enterprise_knowledge` (D6 revised).
- **enterprise_knowledge library coupling** — garage_copilot imports its scripts; upstream changes
  can break the demo. Mitigation: fallback is copying a trimmed script subset (D6); pin behavior
  with garage_copilot's own unit tests.
- **Qdrant infra dependency (new)** — index/retrieval needs a running Qdrant. Mitigation: add to
  the local docker services (alongside db/redis); health check in Task 1.1b validates.
- **Demo credibility** — thin corpus makes copilot say "I don't know" too often. Mitigation:
  labeling discipline (D2) plus corpus deliberately deep on the demo scenario.

## Resources Needed
**What do we need to succeed?**

- LLM API key (OPENAI_API_KEY per repo testing rule) and Atria dev environment (native run;
  per user memory do not build the Atria Docker image locally).
- Automotive reference material for the demo corpus.
- A native Vietnamese speaker for conversation-quality review (Task 4.3).
- Stakeholder session for the M4 demo.
