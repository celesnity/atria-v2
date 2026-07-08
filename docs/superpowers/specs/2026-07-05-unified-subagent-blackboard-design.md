# Unified Subagent on the Blackboard — Design

**Date:** 2026-07-05
**Status:** Approved (brainstorming) — pending implementation plan
**Area:** `atria/core/{agents/subagents,blackboard,divide,parallel,orchestration}`

## Problem

`atria/` exposes three overlapping delegation concepts — **subagent**, **divide**,
and **parallel** — reachable through two redundant LLM-facing entry points:

- `spawn_subagent(strategy=direct|divide|parallel)` + `get_subagent_output`
- `solve(strategy=divide|parallel)` + `get_solve_result`

Both route `divide`/`parallel` through the same orchestrators (`core/divide/`,
`core/parallel/`, `core/orchestration/`). The result is three names for
overlapping machinery, two ways to reach it, and a blackboard
(`core/blackboard/`) that is only advisorily wired in (divide reads its digest
for re-decomposition; parallel solvers get a per-solver handle). The concept
surface is ambiguous.

## Goal

Collapse everything into **one** primitive: the **subagent**. The blackboard
becomes the single source of tasks *and* the shared-context store. The main
agent writes flat, independent tasks to the blackboard and dispatches subagents
(always via the TaskIQ worker) that pull those tasks, execute in isolation, and
write results back as shared-context notes.

### Decisions locked during brainstorming

- **Scope:** full merge — single tool surface *and* blackboard-as-backbone.
- **Parallel/judge:** dropped entirely. Every task is done once by one subagent.
  Delete most of `core/parallel/`.
- **Task creation:** the main agent writes tasks directly. No LLM decomposer.
- **Dependencies:** none. Tasks are a flat, independent pool. Ordering is the
  agent's job via waves (write batch → collect → write next batch).
- **Execution:** always dispatch to the TaskIQ worker. Redis + a running
  `atria-worker` become required for any delegation.

## Architecture

### 1. Concept & tool surface

"Subagent" is the only delegation primitive. `divide` and `parallel` disappear
as user- and LLM-facing concepts.

LLM-facing tools collapse from four to two:

- `subagent(tasks=[{type, prompt}, ...])` — writes one or more flat, independent
  tasks to the blackboard and dispatches workers to pull them. A single
  delegation is just `tasks=[one]`. Returns a `job_id`.
- `get_subagent_output(job_id)` — collects results (the notes subagents wrote
  back) plus per-task statuses.

Removed: `solve`, `get_solve_result`, and the `strategy` parameter on
`spawn_subagent` (which is renamed `subagent`).

### 2. Blackboard task channel & data flow

The existing `Note` channel (append-only, Redis key `atria:bb:{run_id}`) stays
as the **shared-context / results channel**. A **task channel** is added
alongside it.

New `Task` model (`core/blackboard/models.py`), stored under
`atria:bb:{run_id}:tasks`:

- `id` (short id), `subagent_type`, `prompt`,
  `status` (`pending|claimed|done|failed`), `result_ref`, `ts`.

**Atomic claim.** Workers claim via Redis so two workers never grab the same
task — `LMOVE` from `:tasks:pending` to `:tasks:claimed` (or `SETNX` claim flag
per task id). This replaces the divide scheduler's release logic with a simple
pull.

**Per-run data flow:**

1. Main agent calls `subagent(tasks=[...])` → tasks pushed to `:tasks:pending`;
   a job record saved via the existing `JobStore`.
2. Worker(s) pull pending tasks; each runs the named subagent type in isolated
   context, provisioned with a per-run blackboard handle
   (`make_solver_blackboard`) so it reads the shared digest and writes notes back.
3. On finish, the worker marks the task `done`; the subagent's summary lands as
   notes (e.g. `PATCH_SUMMARY`, `OBSERVED`) on the shared context.
4. `get_subagent_output(job_id)` renders the digest of notes produced for that
   job plus per-task statuses.

Notes remain capped and gated by the existing admission/verifier logic —
subagent results are subject to the same hygiene.

### 3. File-level plan

**Deleted outright:**

- `core/parallel/` — entire directory (candidate racing, judge, apply-winner,
  snapshot).
- `core/divide/decompose.py` — LLM decomposer.
- `core/divide/scheduler.py` — DAG scheduler.
- Prompt sections: `tool-solve.md`, `tool-get-solve-result.md`, and the
  `strategy` guidance in `main-subagent-guide.md`.

**Refactored:**

- `core/divide/orchestrator.py` → generalized into a **subagent fan-out
  orchestrator** (dispatch tasks to worker, track job, collect notes), moved to
  `core/subagents/orchestrator.py` (or `core/orchestration/`). Drops
  decompose/schedule calls; keeps the worker-dispatch + digest-read loop.
- `registry_mixins/orchestration_ops.py` → collapse `_execute_solve*` /
  `_execute_divide*` / `_get_parallel_orchestrator` / `_get_divide_orchestrator`
  into a single `_execute_subagent` + `_get_subagent_output` path. This is the
  *only* importer of the deleted dirs, so the delete is clean.
- `subagent_ops.py` → `_execute_spawn_subagent` loses `strategy` and
  `_dispatch_via_orchestrator`; becomes the task-writer + dispatcher.
- `agents/subagents/task_tool.py` → `spawn_subagent` renamed `subagent`,
  description rewritten, `tasks[]` signature.
- `orchestration_tools.py` schemas → remove `solve`/`get_solve_result`, add the
  `subagent`/`get_subagent_output` pair.
- `core/blackboard/models.py` → add `Task` + status; `store.py` → add task-list
  push/claim helpers.

**Kept as-is:** TaskIQ worker + Redis dispatch,
`core/orchestration/{job_store,bridge,gating}.py`, the subagent-type definitions
(`solver`, `module_worker`, `code_explorer`, etc.), the blackboard
admission/verifier gates.

### 4. Execution, worker & result collection

**Always-worker dispatch.** `subagent(tasks=[...])` writes tasks to
`:tasks:pending` and enqueues **one worker job per task** via the existing
TaskIQ/Redis path —
the same infra `divide` uses today, minus decompose/schedule. Redis + a running
`atria-worker` become required for any delegation. Keep the
`ListQueueBroker socket_timeout=None` fix already in place.

**Isolation.** Each worker runs its subagent type in its own context/process,
provisioned with a per-run blackboard handle pointed at the same `run_id`, so all
subagents in a wave share one context and read each other's committed notes.

**Result collection.** `get_subagent_output(job_id)`:

- Loads the job record (`JobStore`), reads per-task statuses from `:tasks:*`.
- Renders the notes those tasks wrote back (`render_digest`).
- Returns `{status, tasks: [{id, type, status}], digest}`. Blocks/polls until all
  tasks are `done|failed` or a timeout, mirroring today's `get_solve_result`.

**Failure handling.** A crashed/failed worker marks its task `failed` (visible in
collection); it does not wedge the wave — other tasks proceed since there are no
dependencies. The agent decides whether to re-issue.

## Testing

- **Unit:** `Task` model + serialization; atomic claim (two workers, one task, no
  double-claim); orchestrator fan-out drains pending; `get_subagent_output`
  aggregates statuses + digest; registry exposes `subagent`/`get_subagent_output`
  and no longer exposes `solve`/`divide`/`parallel`.
- **E2E (real API, per CLAUDE.md):** with `OPENAI_API_KEY` + Redis +
  `atria-worker` running — issue `subagent(tasks=[two independent tasks])`,
  confirm both run on the worker, write notes back, and `get_subagent_output`
  returns both results from the shared context. Verify removed tools are gone
  from the schema.

## Out of scope

- Task dependencies / DAG scheduling.
- Candidate racing, judging, and winner-apply (parallel).
- In-process (no-Redis) delegation path.
- LLM-driven decomposition of a request into sub-tasks.
