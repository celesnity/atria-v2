# data_copilot — Persona Clustering Pipeline (persona.json output)

**Date:** 2026-07-03
**Status:** Design — awaiting user review
**Module:** `modules/data_copilot/`
**Reference:** `.reference/data-agent` (triadic_dgm persona flow)

## 1. Motivation

`data_copilot` today answers ad-hoc data questions and returns a generic
summary: `report` (markdown), `code`, `figures`, `result_table` (`result.csv`),
`suggestions`, `verdict`, `verified` (`scripts/copilot.py::run_analysis`,
lines ~239-252). It has **no structured, machine-readable "persona" artifact**.

The `.reference/data-agent` project produces customer **personas** (clusters)
as a JSON array flowing through stdout markers `[JSON_START_PERSONA] … 
[JSON_END_PERSONA]` (`triadic_dgm/prompts/prompts.py:387`), enforced by its
`SemanticVerifier` (`verifier.py:289`), then parsed by
`report_generator.render_markdown` (`report_generator.py:296`) into a rich
enterprise markdown report. Notably, data-agent **never persists** that persona
JSON to disk — it is an in-memory contract between generated code and the
report generator.

**Goal:** port the persona *pipeline* into `data_copilot` and make a persisted
**`persona.json`** the final deliverable — going one step beyond the reference,
which keeps personas in-memory only.

## 2. Decisions (from brainstorming)

- **Scope:** port the whole persona pipeline (clustering + business rules +
  risk tier + recommended actions + narrative report), not just a file dump.
- **Entry point:** *both* — a dedicated `persona` subcommand **and** SKILL.md
  guidance so the main agent chooses `persona` vs `analyze`.
- **Domain:** domain-agnostic core **+ optional domain pack** (telecom) toggled
  by `--domain telecom`. FTEL-specific rules/catalogs live only in the pack.
- **Output location:** per-session **run dir** (same place as `result.csv`,
  figures), path returned in the summary — consistent with the current flow.
- **Schema fidelity:** **keep data-agent field names** for compatibility;
  domain-specific numeric measures (arpu/churn) appear only when the dataset
  actually has them.

## 3. Architecture

The persona pipeline mirrors `run_analysis`'s generate→run→repair→verify loop
and **reuses existing infra** via dependency injection: `profile`, `sandbox`,
`guardrails`, `client` (role chat / core LLM), `charts`, `audit`, `paths`. No
hardcoded branching of LLM control flow (per CLAUDE.md) — the main agent decides
which subcommand to call; inside the pipeline the loop is dynamic.

### New modules (`modules/data_copilot/scripts/`)

- **`persona_generate.py`** — code-generation prompt for clustering. Instructs
  the model to write a single self-contained pandas/sklearn script that:
  clusters the dataset, computes per-cluster stats, and **prints the persona
  array as JSON wrapped in `[JSON_START_PERSONA] … [JSON_END_PERSONA]`** to the
  exact schema in §4. Also saves a flat persona table to `result.csv` and any
  figures. Domain-agnostic; the telecom pack can append extra guidance.
  Mirrors `generate.py` (same `build_messages`/`generate_code`/`extract_code`
  shape, injecting profile + prior_error + hypotheses for repair/revision).

- **`persona_schema.py`** — schema definition + validation (ports data-agent's
  `ReportValidator` + `report_schema.py`). Required fields per persona:
  `cluster_id`, `persona_name`, `support`, `support_pct`, `confidence`,
  `priority_score`, `is_anomaly`, `segmentation_quality`, `evidence` (dict),
  `recommended_actions` (list), `profile_attributes` (dict), `risk_tier`,
  `sample_persona_text`. Optional numeric measures (e.g. `arpu`, `churn_rate`)
  validated only when present. `validate(personas) -> None` raises on violation;
  `extract_personas(stdout) -> list | None` pulls & json-loads the marker block.

- **`persona_verify.py`** — domain-agnostic anti-hallucination rules ported from
  `SemanticVerifier` (`verify.py` handles generic semantic verify; this adds the
  persona-specific ones): (a) valid JSON persona block present; (b) evidence-first
  — each persona's `evidence` features deviate ≥20% from global mean; (c) no
  causal hallucination (no invented external causes); (d) priority_score must
  carry an explainable formula; (e) anomaly gate (tiny clusters flagged LOW /
  `is_anomaly`); (f) silhouette sanity (warn on inflation by anomaly cluster).
  Returns a verdict `{"status": "OK"|"REVISE", "hypotheses": str, "warnings": []}`
  matching the existing verdict shape. `load_domain_pack(name)` extends the rule
  set (telecom adds FTEL causal/evidence-alignment/dBm rules).

- **`persona_report.py`** — ports `render_markdown`: `validate` → global means →
  rank by `priority_score` → LLM narrative (via core `client` role chat, not
  instructor) → compose markdown. Narrative sections: executive summary,
  per-persona analysis, recommendations, conclusion. Telecom pack adds
  `ROADMAP_METADATA` / `RETENTION_SCRIPT_CATALOG` mapping.

### Orchestrator — `persona.py::run_persona(...)`

Signature mirrors `run_analysis`, with injectable deps
(`codegen_fn`, `verify_fn`, `report_fn`, `profile_fn`, `guard_fn`, `exec_fn`,
`domain`, `k`, `timeout`, `max_output`, `max_repair`, `max_verify`, `out_dir`):

1. `prof = profile_fn(dataset)` (resolve absolute path first).
2. Loop: `persona_generate` → guardrails → sandbox exec.
3. Repair loop on execution error (`max_repair`), feeding stderr back.
4. `extract_personas(stdout)`; if missing → REVISE with the marker instruction.
5. `persona_verify` (+ domain pack); on REVISE feed hypotheses back (`max_verify`).
6. On OK: `validate` → **write `persona.json`** → `persona_report` → write
   `persona_report.md`; load `result.csv` for chart suggestions (reuse
   `charts.detect_suggestions`).
7. `audit.append_event({type: "persona", ...})`.
8. Return summary (§5).

## 4. Persona JSON schema (`persona.json`)

A JSON array; each element:

```json
{
  "cluster_id": 0,
  "persona_name": "string",
  "support": 1234,
  "support_pct": 0.27,
  "confidence": "HIGH|MEDIUM|LOW",
  "priority_score": 0.0,
  "is_anomaly": false,
  "segmentation_quality": "NORMAL|LOW|...",
  "risk_tier": "string",
  "evidence": { "feature": 12.3 },
  "profile_attributes": { "feature": "value" },
  "recommended_actions": ["string"],
  "sample_persona_text": "string"
}
```

Optional domain measures (`arpu`, `churn_rate`, `severity`, `risk`) included only
when derivable from the dataset. Field names match data-agent for compatibility.

## 5. Output contract (subcommand summary)

`copilot.py persona …` prints one JSON object (parsed by the main agent):

```json
{
  "dataset": "...", "question": "...", "domain": "telecom|null",
  "code": "...", "status": "ok|error",
  "verified": true, "verdict": { ... },
  "personas": [ ... ],            // inline persona array
  "persona_json": "<run_dir>/persona.json",   // persisted deliverable
  "report": "<markdown>",
  "figures": ["..."],
  "result_table": "<run_dir>/result.csv",     // flat persona table
  "suggestions": [ ... ],         // chart configs for send_table
  "repairs": 0, "verify_rounds": 0
}
```

Artifacts written to the per-session run dir: `persona.json`, `persona_report.md`,
`result.csv`, `result.meta.json`, figures.

## 6. CLI & Skill

- **CLI:** `copilot.py persona "<abs path>" "<question>" [--domain telecom]
  [--k N] [--max-repair N] [--max-verify N] [--out DIR]`. `--k` optionally pins
  cluster count; default lets the code choose (silhouette-based).
- **SKILL.md:** new section — clustering/persona/segment questions → use
  `persona` (not `analyze`); it emits `persona.json` + a narrative report; present
  the report, call `send_table` with `result_table`; if `verified=false`, say so
  and do not present numbers as settled.
- **audit:** new event type `persona`.

## 7. Testing (per CLAUDE.md — both required)

- **Unit (`uv run pytest`):** `persona_schema.validate` (accept/reject),
  `extract_personas` (marker parsing, malformed JSON), `persona_verify` rules
  (each rule fires on a crafted output), `run_persona` orchestration with fake
  `chat_fn`/`exec_fn` (repair loop, verify loop, artifact writing).
- **E2E with `OPENAI_API_KEY`:** run `copilot.py persona` on a `sample_data`
  file (and telecom pack on a telecom-shaped sample), confirm a valid
  `persona.json` is written, report renders, `verified=true`.

## 8. Non-goals (YAGNI)

- No self-evolution / RIMRULE memory bank (data-agent's DGM engine).
- No separate Programmer/Verifier/Proposer LLM services — single core LLM via
  role chat.
- No web-UI-specific persona view beyond the existing `send_table`/`send_image`.
- No streaming `<Analyze>/<Execute>` tag protocol (that is data-agent's UI).

## 9. Open questions

- Domain-pack question was left unanswered during brainstorming; proceeding with
  "domain-agnostic core + optional telecom pack". Confirm on spec review.
- `persona.json` location & schema fidelity chosen by best-judgment (run dir +
  data-agent field names). Confirm on spec review.
