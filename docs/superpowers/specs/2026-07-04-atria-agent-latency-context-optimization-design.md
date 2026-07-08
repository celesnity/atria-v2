# Atria Agent — Speed / Latency / Context Optimization

**Date:** 2026-07-04
**Status:** Approved design, ready for implementation plan
**Scope:** `atria/` main agent only. The RAG / vector-search work lives in separate
modules (`modules/maintenance_copilot`) and is explicitly **out of scope** — it must
stay out of the agent's hot path, not be optimized here.

## Goal

Reduce the atria agent's per-turn latency and per-call context size by (A) enabling
prompt-prefix caching on the OpenAI-compatible request path, (B) cutting forced extra
LLM round-trips in the ReAct loop, and (C) trimming dead / dormant modules that add
import, startup, and prompt-context weight. No new subsystems. Every change is
independently shippable, independently revertable, and gated so default behavior is
preserved unless explicitly enabled.

## Context / Findings (current state)

Two investigations mapped the hot path. Key facts driving this design:

- **ReAct loop** (`atria/core/agents/main_agent/run_loop.py`, `RunLoopMixin.run_sync`):
  single `while True:` with `max_iterations` defaulting to `None` (unlimited). Forced
  extra round-trips: a mandatory `implicit_completion_nudge` before accepting any
  implicit completion (`run_loop.py:432-485`), up to `MAX_TODO_NUDGES=4` and
  `MAX_NUDGE_ATTEMPTS=3`. Every turn also force-runs a `Code-Explorer` subagent before
  most subagent work (`run_loop.py:546-584`).
- **No streaming** anywhere — first-token latency = full-completion latency.
- **Doubly-nested retry:** run_loop retries 429/5xx with 2/5/10s sleeps
  (`run_loop.py:315-375`) *and* `http_client.post_json` retries with 1/2/4s backoff.
- **Prompt caching not effective.** Provider is OpenAI-compatible (mixed/unknown server:
  vLLM / OpenAI / LM Studio all possible). There is no Anthropic `cache_control` to emit;
  these servers do **automatic prefix caching** of the longest unchanged request prefix.
  Today the prefix is not treated as stable and no cache-affinity key is sent, so caching
  rarely engages. The `_system_dynamic` split exists (`run_loop.py:305`) but is a dead
  top-level payload key consumed by nobody.
- **System prompt** ~19 sections / ~10k tokens. `builders.py:198-203` hard-codes
  `has_subagents=True` and `todo_tracking_enabled=True`, so the subagent-guide (~118
  lines) and task-tracking sections always load even when unused.
- **Environment block** (`components/prompts/environment.py`): `EnvironmentContext` is an
  immutable snapshot collected **once at startup**. Despite containing a date and model
  name, it is **session-stable** and therefore safe inside the cached prefix. It is *not*
  a cache-buster. The true per-turn cache-busters are the blackboard "Shared Lessons"
  block and any content recomputed each iteration.
- **Dead / dormant modules:**
  - `atria/core/context_engineering/retrieval/` (`ContextRetriever`, `CodebaseIndexer`):
    built but **no live call site** in the loop.
  - `atria/core/context_engineering/memory/selector.py`: semantic scoring path exists but
    the embedding generator is unwired and `_batch_generate_embeddings` early-returns
    (`selector.py:112-118`); default semantic weight is 0.0 — dormant scaffolding.

## Design Principles

1. **Stable bytes first, volatile bytes last.** The request prefix
   `[stable system prompt][tool schemas]` must be byte-identical across every call in a
   session; anything that changes per turn moves to the tail.
2. **Do work only when a condition warrants it**, not every turn.
3. **Config-gated, default-preserving.** Behavior-changing flags default OFF (current
   behavior). Pure-latency changes (retry de-duplication) may change timing but not
   output.
4. **Measure every change.** No optimization lands without a before/after number.

## Workstream A — Prefix stability (prompt caching)

Provider-agnostic: works for vLLM (`enable_prefix_caching`), OpenAI (auto cache >1024
tokens + `prompt_cache_key`), and LM Studio / llama.cpp (per-slot prompt cache). Servers
that ignore the affinity key simply no-op.

Changes:

- **Audit the request prefix** for any per-turn string. Produce a checklist of every field
  currently in `[system-stable][tool schemas]` and confirm each is session-stable. Known
  keep-in-prefix: env block (startup snapshot), static prompt sections, tool schemas.
  Known move-to-tail: blackboard "Shared Lessons", active-module SKILL block if it changes,
  skills index if regenerated per turn.
- **Reorder in `builders.py` `build_two_part`** so volatile blocks are appended as the
  last system/user content (the "tail"), leaving the prefix untouched between calls.
- **Repurpose the existing `_system_dynamic` split** (`run_loop.py:305`) as the real tail
  carrier instead of a dead key.
- **Add optional `prompt_cache_key`** (stable per session, e.g. session id) to the
  `http_client` payload, config-gated. Servers that don't recognize it ignore it.
- **Tool-schema stability:** ensure tool schemas serialize deterministically (stable key
  order) so the schema portion of the prefix does not change across calls.

Risk: **low** — output-identical; only ordering/keys change. Main gotcha: a single
per-turn string left in the prefix silently defeats caching; the audit checklist guards
this.

## Workstream B — Cut forced round-trips

Changes (each behavior-changing flag defaults to current behavior):

- **`max_iterations`:** default to a finite cap (config'd, e.g. 25) instead of `None`, as
  a runaway guard.
- **`implicit_completion_nudge`** (`run_loop.py:432-485`): gate behind a config flag,
  **default off** so a clean completion does not pay an extra full round-trip. When off,
  accept implicit completion without the extra call.
- **Forced Code-Explorer subagent** (`run_loop.py:546-584`): change from always-on to
  conditional (config flag / heuristic), **default off** so routine turns skip the forced
  nested agent run.
- **Collapse doubly-nested retry:** keep backoff in **one** layer (`http_client`), and
  remove the redundant sleep/retry wrapper in `run_loop` (or vice-versa) so a single
  stalled call cannot stack tens of seconds of nested backoff. Pure-latency change.
- **Reduce `MAX_TODO_NUDGES` / `MAX_NUDGE_ATTEMPTS` defaults** (config'd).

Risk: **medium** — touches loop-termination behavior. Mitigated by default-off flags and
covered by loop unit tests plus a real e2e run.

## Workstream C — Trim dead / dormant modules

Per project rule (CLAUDE.md): **move to `_local/`, do not delete.**

- **`retrieval/`:** grep-confirm zero live imports/call sites, then move
  `atria/core/context_engineering/retrieval/` to `_local/` (preserve, don't delete).
  Update `retrieval/__init__.py` exporters / any `__init__` re-exports accordingly.
- **Dormant semantic memory:** remove the misleading unwired path in `selector.py`
  (the `_batch_generate_embeddings` stub + 0.0-weight semantic scaffolding), or reduce it
  to a single documented flag. Keep `EmbeddingCache` / `cosine_similarity`
  (`memory/embeddings.py`) — they are reusable primitives, just not wired here.
- **Un-hardcode prompt gating:** in `builders.py:198-203`, stop forcing
  `has_subagents=True` / `todo_tracking_enabled=True`. Drive them from actual feature
  availability so the subagent-guide (~118 lines) and task-tracking sections load only
  when relevant — shrinks the cached prefix when unused.
- **`modules/rag` test caveat:** `tests/test_rag_module.py` references a
  `modules/rag/scripts/rag.py` that does not exist on disk. Do **not** delete anything
  that test depends on; if it is already failing/stubbed, leave it and note it — out of
  scope for this work.

Risk: **low** (dead/dormant code), but removal is hard to reverse — move (not delete)
only after grep-confirming no imports.

## Testing & Rollout

Per project rules (CLAUDE.md — unit tests **and** real e2e with `OPENAI_API_KEY`):

- **Unit tests** (`uv run pytest`): loop-gating flags (A/B), builder prefix-ordering (A),
  gating un-hardcode (C). Assert prefix bytes are identical across two successive builds
  with a changed volatile tail.
- **Real e2e** with `OPENAI_API_KEY`: run a multi-tool turn through the running agent;
  capture before/after **(a)** input tokens per round-trip, **(b)** round-trips per turn,
  **(c)** wall-clock per turn, using the existing cost tracking (`run_loop.py:381`).
- **One commit per workstream** so any regression is bisectable. No `Co-Authored-By`
  trailer (project convention).

## Success Criteria

- Prefix bytes identical across successive calls in a session (verified in test).
- Measurable input-token reduction per round-trip on a prefix-caching server (A), and
  fewer round-trips per completed turn with default flags (B).
- No dead-code imports remain for moved modules; `make check` and `make test` pass.
- No behavior change for a completed turn unless an opt-in flag is enabled.

## Out of Scope (YAGNI)

- Streaming (larger change, touches UI callbacks) — explicitly deferred.
- Any vector / RAG / embedding retrieval in the agent — lives in separate modules.
- Provider-adapter rewrite — the targeted prefix fix is lower-risk.
