# Design: Port `data_copilot` to the data-agent LangGraph flow + output

**Date:** 2026-07-06
**Status:** Approved (design), pending spec review
**Author:** brainstormed with the user
**Reference:** `/home/anlnm/duynvt/.reference/data-agent` (`langgraph_agent/{graph,nodes,state}.py`, `triadic_dgm/{agent/verifier,services/report_generator,schemas/report_schema,prompts/prompts,sandbox/kernel}.py`, `ui/display.py`)

## 1. Goal & non-goals

**Goal.** Replace the current linear `analyze`/`persona` loops in `modules/data_copilot/` with a faithful port of the data-agent's 10-node LangGraph flow, hosted as a CLI with durable checkpointing, producing the reference's **verbatim** telecom persona report and semantic gates. Make the Atria core (`atria/`) interact cleanly with the new two-step (`run` → `resume`) human-in-the-loop (HITL) contract.

**Non-goals / explicit exclusions.**
- The reference's DGM/evolution system (`triadic_dgm/benchmark`, `evolution_dgm`, `dgm_agent_v2`).
- The RIMRULE memory bank. Memory is disabled by default per `CLAUDE.md`; `verify_syntax` becomes a plain LLM inspector with **no** memory persistence.
- The Gradio UI and the reference's `api_server.py` (SSE service).
- Web-native driving of the graph (new REST/WS lifecycle routes + React plan-review UI) — deferred; see §10 "Deferred".

## 2. Decisions (locked during brainstorming)

1. **Execution engine:** adopt LangGraph + a stateful Jupyter kernel (faithful port), *not* the current subprocess loop.
2. **Hosting/invocation:** CLI + durable `SqliteSaver` checkpointer. Not a long-running service. `run` starts the graph to the plan interrupt; `resume` reopens the checkpoint and continues. The kernel is restarted per invocation and prior cells replayed.
3. **Domain coupling:** port the telecom churn specifics **verbatim** (catalogs, ~12 gates, 6-section composer, `ReportNarrative`). `data_copilot` becomes a telecom-churn persona tool at full output parity; a generic fallback keeps non-persona questions usable (§6.5).
4. **Entry points:** one unified graph command **replaces both** `analyze` and `persona`. `ingest`/`datasets`/`profile`/`audit` are kept.
5. **Port structure:** Approach B — adapted port. Flat `scripts/` layout, bind LLM calls to the existing `RoleClient`/`config`, reuse `profile`/`ingest`/`guardrails`/`audit`/`charts`. "Verbatim" applies to output/gate **content**, not the agent scaffolding.
6. **Atria integration depth:** Option 1 — agent-driven HITL (SKILL.md runbook + path resolvers + a surfacing tool + a read endpoint). No new frontend.

## 3. Architecture — module layout

Flat `modules/data_copilot/scripts/`. **New files:**

- `graph.py` — `StateGraph` builder + conditional edges (mirrors `langgraph_agent/graph.py`).
- `nodes.py` — the 10 node functions, bound to `RoleClient` (mirrors `langgraph_agent/nodes.py`).
- `state.py` — `AgentState` TypedDict (mirrors `langgraph_agent/state.py`) + `executed_cells`.
- `kernel.py` — stateful `jupyter_client` kernel wrapper (from `triadic_dgm/sandbox/kernel.py`), with the env-scrub already applied to the subprocess sandbox carried over.
- `report_generator.py` — verbatim 6-section composer + catalogs.
- `report_schema.py` — `ReportNarrative` pydantic schema for `instructor` structured output.
- `gates.py` — the ~12 deterministic `verify_semantics` gates + `is_business_task` + LLM `verify_syntax` (no memory bank).
- `prompts.py` — `PLANNER_PROMPT`, `CLASSIFIER_PROMPT`, `CRITIC_PROMPT`, `SEMANTIC_FIX`, `RESULT_PROMPT`, programmer prompt.

**Reused as-is:** `client.py`, `config.py`, `profile.py`, `ingest.py`, `guardrails.py`, `audit.py`, `charts.py`, `paths.py`.

**Retired:** the linear `persona.py`/`run_persona` and `run_analysis` loops in `copilot.py`, `verify.py` (LLM OK/REVISE judge), and `persona_verify.py` (superseded by `gates.py`). `persona_report.py`/`report.py` fold into `report_generator.py` (the latter's grounded-markdown path stays as the generic fallback).

**New dependencies (add to `requirements.txt`):** `langgraph`, `langgraph-checkpoint-sqlite`, `jupyter_client`, `ipykernel`, `instructor`, `Pillow`.

## 4. Graph flow (mirrors the reference exactly)

```
generate_plan → human_review(interrupt) → classify_review
   ├ APPROVE → generate_code
   └ REJECT/CLARIFICATION → generate_plan
generate_code → code_critic
   ├ PASS → execute_code
   └ FAIL → generate_code
execute_code
   ├ ok           → semantic_verify
   ├ error, <4    → repair_code → execute_code
   └ error, ≥4    → generate_report
semantic_verify
   ├ ACCEPT or attempts≥5 → generate_report
   └ REVISE                → semantic_fix → execute_code
generate_report → END
```

Retry budgets aligned to the reference: **syntax = 4, semantic = 5** (replacing the current `max_repair=3`, `max_verify=2`).

### Node → LLM-role binding

- `generate_plan`, `generate_code`, `code_critic`, `classify_review`, repair-regen, fix-regen → **codegen** role.
- `verify_syntax` (inspector) → **verify** role.
- `ReportNarrative` narrative → **report** role (wrapped by `instructor`).
- `is_business_task` (keyword) and all semantic gates are deterministic — no LLM.

## 5. State (`AgentState`)

Ported from `state.py`: `messages`, `user_task`, `analysis_plan`, `review_status`, `review_feedback`, `review_history`, `generated_code`, `critic_verdict`, `exe_result`, `exe_sign`, `syntax_attempts`, `semantic_attempts`, `verdict`, `inspector_hypotheses`, `final_report`, `error_message`.

**Addition:** `executed_cells: list[str]` — the ordered code cells successfully executed so far. Needed because the reference keeps its process (and kernel) alive between interrupt and resume, whereas this CLI does not: on `resume`, a fresh kernel is started and `executed_cells` replayed in order before continuing. (`chat_history_display` from the reference is dropped; progress goes to stderr instead — §6.6.)

## 6. Output shapes

### 6.1 Verdict vocabulary → reference
`{status: "ACCEPT"|"REVISE", missing: [...], feedback: "", epiplexity_score: float}` replaces the current `{status: "OK"|"REVISE", hypotheses}`.

### 6.2 Persona JSON schema
Baseline already partly moved by commit `d4a969d` (`risk`, `feature_means`, `persona_type` lenient; `sample_persona_text` dropped). Remaining additions for composer parity:
- `severity` (e.g. `LOW|MEDIUM|HIGH|EXTREME`).
- Richer `profile_attributes` sub-keys read by the composer: `service_composition`, `package_composition`, `csat_avg`, `ces_avg`, `tier_upgrade_rate`, `tier_downgrade_rate`, `usage_decline_strong_pct`, `usage_decline_mild_pct`, `usage_unstable_pct`, `status_worsening_pct`, `high_spender_pct`, `avg_fee`, `loyalty_rank_avg`.
- `recommended_actions[0]` **must** be one of the 10 `ROADMAP_METADATA` keys (so the roadmap table populates owner/timeline/KPI).

`persona_generate.py` prompt and `persona_schema.py` updated accordingly (lenient validation for optional fields, strict for the core set).

### 6.3 Report (verbatim 6-section composer)
`report_generator.py` produces, deterministically, from the persona JSON + catalogs: Executive Summary → Methodology → Persona Overview (icon cards) → Risk Tier Grouping → Persona Analysis (per-persona tables: signals, service composition, business interpretation, operational impact, profile attributes, retention scripts) → Business Roadmap (priority table) → Conclusion → Appendix (cluster feature statistics + raw facts JSON). The LLM fills only the `ReportNarrative` slots (`executive_overview`, `business_interpretation`, `operational_impact`, `conclusion`).

### 6.4 Suggestions
Port the reference's `display_suggestions`: parse `"Next, you can: [n] ..."` from the model output into markdown options. The existing heuristic `charts.py` chart suggestions are unaffected (they feed the web chart UI) and continue to flow via the surfacing tool.

### 6.5 Generic (non-persona) fallback
When `generate_report` finds no `[JSON_START_PERSONA]` block, it falls back to a grounded-markdown report (the current `report.py` behavior folded in) instead of the reference's error string — so non-persona questions ("sum revenue by region") still produce a usable report. Deliberate deviation from the reference, accepted during brainstorming.

### 6.6 Progress & JSON contract
Progress markers go to **stderr** (existing `_progress` pattern); the final result is a single JSON object on **stdout**, preserving the SKILL.md parse contract.

## 7. Telecom parity (verbatim)

Copied faithfully from `report_generator.py` and `verifier.py`:
- `ROADMAP_METADATA`, `RETENTION_SCRIPT_CATALOG`, `FEATURE_SEMANTIC_MAP`, `EXCLUDED_TECHNICAL_FEATURES`, `_DIRECTIONAL_FLAG_FEATURES`, `CONFLICTING_FEATURE_PAIRS`, `ReportValidator`, `attach_recommended_scripts`, and all composer helpers.
- The ~12 semantic gates: `RMDT` target-leakage, geography dominance (`khu_vuc`/`goi_cuoc`/`ma_su_co_pho_bien`), K ≥ 3, silhouette < 0.2, ARPU floor, short/duplicate persona names, `(Cụm X)` naming ban, causal hallucination, dBm good/bad threshold ban, priority-formula transparency, fake-persona (single cluster) ban, increase-K suggestion ban, outlier (<1%) naming, business-hallucination (feature not in model), action↔evidence contradiction.

With `--domain telecom` off, telecom-specific gates are skipped and the composer degrades to generic sections only.

## 8. Execution model (CLI + durable checkpointer)

- `copilot.py run <dataset> <question> [--domain telecom] [--k N]`
  → resolve dataset → profile → build graph with `SqliteSaver` (db under the session `runs/` dir, keyed by a generated `thread_id`) → run to the `human_review` interrupt
  → stdout: `{"status":"awaiting_review","thread_id":"...","plan":"..."}`.
- `copilot.py resume --thread <id> --feedback "<text>"`
  → reopen checkpoint → start fresh kernel, replay `executed_cells` → `Command(resume=feedback)` → run to next interrupt or `END`
  → stdout: `{plan}` again if re-planning, else the final `{report, verdict, personas, persona_json, figures, result_table, suggestions, repairs, verify_rounds, ...}`.
- Kernel env is scrubbed exactly like the current subprocess sandbox (allow-list, no API keys), applied to the `jupyter_client` kernel subprocess.

## 9. Atria integration (Option 1 — agent-driven)

The agent remains the orchestrator and mediates HITL in chat.

- **SKILL.md runbook rewrite:** document the `run` → show plan to user → `resume --thread <id> --feedback <reply>` loop; replace the `analyze`/`persona` sections; keep `ingest`/`datasets`/`profile`/`audit`.
- **`atria/core/modules/data_copilot_paths.py`:** add resolvers for the new session-scoped artifacts — `report.md`, `persona.json`, the plan text, and the checkpoint db — so tools/routes can locate them (mirroring the existing CSV resolvers).
- **Surfacing:** extend the existing `send_table` flow or add a small `send_report` tool so the agent can push the final report markdown + personas to chat (the result table + charts already flow via `send_table`). The interim plan is shown as plain chat text for review.
- **`atria/web/routes/data_copilot.py`:** add a read endpoint for the report/persona artifacts so the web can render them (mirroring the existing `/read`).
- **`disabled_tools.py`:** unchanged (`send_table` stays enabled; `solve`/`memory` stay off). Add `send_report` to the enabled set if introduced.

## 10. Deferred (web-native, not built)

Documented for a later phase, explicitly out of scope now: `/api/data-copilot/run` + `/resume` REST routes, WebSocket node-update events, and a React plan-review UI so the web app drives the graph directly (closer to the reference SSE `api_server`).

## 11. Testing

Unit (injectable, LLM-free, matching the current test style):
- Graph routing — each conditional edge (`_after_classify`, `_after_critic`, `_after_execute`, `_after_verify`).
- Gates — each rule pass/fail on crafted persona JSON + stdout.
- Composer — golden-markdown snapshot from a fixed persona JSON (the six sections + appendix).
- Schema — validation of the expanded persona schema (strict core, lenient optional).
- Kernel — start/execute/capture, and replay-from-`executed_cells` fidelity.
- Checkpointer — `run` persists → `resume` reopens the same `thread_id`.
- CLI — `run` returns `awaiting_review` + `thread_id` + `plan`; `resume` returns the final report JSON; error paths emit clean `{"error"}` JSON.
- Atria — `data_copilot_paths.py` resolvers, the report read endpoint, and the surfacing tool.

E2E (per `CLAUDE.md`, requires `OPENAI_API_KEY`): a real `run` → `resume` → report cycle on a sample dataset. Deferred until a key is available in the environment.

## 12. Phasing (each phase independently testable + reviewable)

1. **Scaffolding & vocab:** `state.py`, deps in `requirements.txt`, verdict vocab (`ACCEPT`/`feedback`), budgets 4/5.
2. **Kernel:** `kernel.py` stateful executor + env-scrub + replay, behind the existing `exec_fn` seam.
3. **Gates + schema:** `gates.py`, expanded persona schema/prompt (`severity`, richer `profile_attributes`, roadmap-key action).
4. **Report:** `report_schema.py` + `report_generator.py` (verbatim) + generic fallback.
5. **Graph:** `graph.py`, `nodes.py`, `prompts.py`, `SqliteSaver` checkpointer.
6. **CLI + Atria:** `run`/`resume`, retire `analyze`/`persona`, SKILL.md rewrite, `data_copilot_paths.py` resolvers, surfacing tool, report read endpoint.

## 13. Key risks

- **Kernel replay cost/faithfulness** — replaying all cells on every resume re-runs prior work; accepted per the hosting choice, but slow for long analyses and assumes deterministic re-execution.
- **New heavy deps** — `jupyter_client`/`ipykernel`/`langgraph` enlarge the module footprint and Docker image.
- **Verbatim telecom coupling** — the output is Vietnamese/telecom-specific; generic datasets get the thinner fallback report.
- **Contract change** — invocation moves from one call to `run` + `resume`; the agent (SKILL.md) and any existing `analyze`/`persona` callers must be updated.
- **Checkpoint/thread lifecycle** — orphaned `SqliteSaver` rows and run dirs accumulate; needs a cleanup/TTL story (call out in implementation).
