# Agent-Level Bench Report — {{DATE}}

<!--
  Canonical report template for testing (adopted from the 2026-07-08 enterprise
  Agent-Level Bench Report; the original is preserved verbatim at the bottom as a
  format reference). pub_bench.py fills every double-brace placeholder below. Keep the
  section structure and the "Failures" line convention stable across runs so
  reports are diff-able.
-->

- Agent under test: {{AGENT_DESC}}
- Judge: {{JUDGE_DESC}}
- Harness: {{HARNESS_DESC}}
- Discipline: measure-only. No retrieval/prompt tuning from these results.

## Maps Public Evaluation ({{N_CASES}} cases)

Source: `ai_maps_track1_dataset_participants_v2.xlsx` → sheet "Public Evaluation"
(`PUB001..PUB{{LAST_ID}}`), mirrored verbatim in `data/eval_queries.json`. Output
contract (README): `normalized_query, intent, entities, confidence_score`.

### Deterministic baseline (router vs PUB gold — free, reproducible)

Backends compared: {{BASELINE_BACKENDS}}. Gate backend: {{GATE_BACKEND}}.

- intent_acc: {{INTENT_ACC}}
- poi_hit@1 / @3: {{POI_HIT1}} / {{POI_HIT3}}
- category_acc: {{CATEGORY_ACC}}
- norm_match (informative — ours is accent-folded by design): {{NORM_MATCH}}
- city_precision: {{CITY_PRECISION}}
- anchored_pass: {{ANCHORED_PASS}}
- entity-extraction coverage (cases whose expected entity key is resolved): {{ENTITY_COV}}
- latency p50 / p95: {{LAT_P50}} / {{LAT_P95}}
- coverage gaps (expected POI absent from the participant dataset): {{COVERAGE_GAPS}}
- Gates: {{GATES}}

intent_acc by expected intent:
{{INTENT_BY_INTENT}}

intent_acc by difficulty:
{{INTENT_BY_DIFFICULTY}}

### Agent-level pass (real Jarvis pipeline + LLM judge)

Compound gate = places search used AND router intent correct AND judge marks the
answer/behavior correct. The Jarvis pipeline answers simple intents on a
deterministic fast path (no LLM); reasoning / ambiguous / "why·best·compare"
queries fall through to the real ReAct agent.

Read the compound pass together with `behavior_ok`: the gate also requires the
router's intent label to equal the gold label, and several gold labels are
internally inconsistent (e.g. a named landmark tagged Category vs POI), so a case
can have a correct answer (`behavior_ok`=true) yet miss the gate on the label
alone. The judge runs at temperature 1 (gpt-5 family disallows 0) with a fixed
seed, so verdicts can shift by a few cases run-to-run.

- Pass (compound gate): {{AGENT_PASS}}
- behavior_ok (judge answer-correctness, independent of the intent-label gate): {{BEHAVIOR_OK}}
- places source used: {{PLACES_USED}}
- fast-path / agent-path split: {{PATH_SPLIT}}
- map_action_ok (actions fit the intent: pins·route·focus): {{MAP_ACTION_OK}}
- Recommendation/POI name-recall (any expected name in answer): {{NAME_RECALL_ANY}}
- Recommendation/POI name-recall (individual names): {{NAME_RECALL_IND}}
- Run errors (agent crash / empty reply): {{RUN_ERRORS}}
- Judge errors (verdict unavailable): {{JUDGE_ERRORS}}

Pass rate by expected intent:
{{PASS_BY_INTENT}}

Pass rate by difficulty:
{{PASS_BY_DIFFICULTY}}

Failures:
{{FAILURES}}

## Runtime

- Cases run: {{CASES_RUN}}
- Median wall per case: {{MEDIAN_WALL}}; total: {{TOTAL_WALL}}

<!-- ============================================================= -->
<!-- Reference — original pasted template (2026-07-08 enterprise deployment). -->
<!-- Kept verbatim as the format source; NOT part of the generated maps report. -->
<!-- ============================================================= -->

<details>
<summary>Reference format — original enterprise Agent-Level Bench Report (2026-07-08)</summary>

```markdown
# Agent-Level Bench Report — 2026-07-08

- Agent under test: real Atria ReAct loop, model `gpt-5-nano` (bench override)
- Judge: `gpt-5-mini` at temperature 0 (separate from agent model)
- Harness: scripts/agent_bench/ — headless stack, per-case identity via ATRIA_SEARCH_USER_ID
- Discipline: measure-only. No retrieval/prompt tuning from these results.

## Track 1 — Enterprise Knowledge (50 cases)
- Allow pass (compound gate: search used + retrieval hit + answer correct): 24/43 (56%)
- Deny pass (compound gate: search used + refused + no leak): 5/7 (71%)
- Allow pass rate by answer_type: Exact 13/27, Multi-document 1/1, Semantic 3/6, Summary 7/9
- Failures: P005 [Allow/Semantic] ks=True hit=True err=False: <reason> ...

## Track 8 — Maps Assistant (30 cases)
- Pass (compound gate: places search used + intent + behavior): 26/30 (87%)
- Pass rate by conversation category: Conversational Search 7/7, Long Conversation 0/1 ...
- Failures: P022 [Multi-turn Search] ks=False rec=0/1 err=False: <reason> ...

## Runtime
- Median wall per case: 87.3s; total: 135.6 min
```

</details>
