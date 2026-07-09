# Blackboard Broadcast Paradigm — Design

**Date:** 2026-07-09
**Status:** Approved (design), pending implementation plan
**Reference:** *LLM-based Multi-Agent Blackboard System for Information Discovery in Data Science*, Salemi et al., arXiv:2510.01285 (`.references/2510.01285.pdf`)

## Problem

The paper's thesis is a **broadcast-request / voluntary-response** communication paradigm that is explicitly *against* the master–slave paradigm:

- The main agent posts an **un-addressed request** `r` to a shared blackboard `β` ("I need X") — it does not name a sub-agent.
- Helper agents each hold a **capability profile** (built offline) and **autonomously self-select** whether they can answer.
- Volunteered answers land on a **separate response board** `β_r` (kept separate from `β` to prevent cross-influence between helpers — paper footnote 2), then are collected back to the main agent, which decides whether to use them.

Atria's current blackboard is the master–slave design the paper argues against:

- `Task.subagent_type` (`atria/core/blackboard/models.py`) means the main agent *picks the specific worker*.
- `subagent(tasks=[{subagent_type, prompt}])` (`atria/core/agents/subagents/task_tool.py`) requires the caller to route each task.
- The worker is routed to by `payload.subagent_type` (`atria/core/tasks/tasks.py`) — it does not volunteer.
- There is no capability profile.
- The result overwrites `Task.result` in the same hash — there is no separate response board.

**Goal:** flip task-**assignment** into request-**broadcast + autonomous self-selection**, add the separate response board, and build a blackboard viewer that makes the autonomy visible.

## Chosen approach

**Approach A — self-selecting functional helpers**, with a **per-helper autonomous bid**.

Rejected alternatives (documented as future work, not built):
- **B — workspace-cluster file agents** (literal port): partition the workspace into clusters offline, one file-agent per cluster. Faithful to the paper's data-lake domain, but adds a clustering + per-cluster-agent subsystem this repo does not need.
- **C — hybrid** of A and B.
- **Single-router bid** (one LLM reads all profiles and picks helpers): cheaper, but reintroduces a coordinator that knows every capability — exactly what the paper argues against.

## Design

### 1. Data model — `atria/core/blackboard/models.py`

Replace the master–slave `Task` with two records:

- **`Request`** — `{id, prompt, status, ts}`. No `subagent_type`. The paper's un-addressed request `r` on board `β`. Status: `open → answered → closed`.
- **`Response`** — `{request_id, responder, content, confidence, ts}`. The paper's `β_r` entry. Stored in a store **separate** from the note channel so helpers cannot cross-influence.

`Note` and the admission verifier (`admission.py`, `verify_llm.py`) stay exactly as-is. They guard the shared *note* channel `β`, which remains how helpers publish durable findings. Responses are **not** admission-gated — the main agent judges responses itself, per the paper.

### 2. Capability profiles — `atria/core/agents/subagents/agents/*.py`

Add `capability_profile: str` to each subagent spec: a 1–2 sentence offline description of what that helper can do / owns (the paper's offline phase). Examples:
- Planner → "explores and maps code, finds patterns and definitions."
- Web-Generator → "builds React/TypeScript/Tailwind UIs."
- module_worker → "implements changes within a single module."

`ask-user` is a builtin UI action, **not** a volunteer — excluded from the bid pool, still directly invokable via its existing path.

### 3. Broadcast + autonomous bid — `atria/core/subagents/orchestrator.py`

When the main agent posts a request:

1. **Broadcast** — write the `Request` to `atria:bb:{run}:requests`.
2. **Bid** — for each helper with a profile, run an **independent** cheap-LLM yes/no self-assessment using *that helper's own profile + the request only* — never a joint view of all profiles, so no coordinator "knows" capabilities. Bids run concurrently, capped by `max_helpers`, **fail-closed** (error/timeout = no volunteer), reusing the existing `verify_llm` cheap-model chain. Each bid (volunteer/decline + one-line reason) is emitted as an event for the viewer.
3. **Fan out to volunteers only** — enqueue the existing TaskIQ worker path (`SubagentTaskPayload`, `manager.execute_subagent`) for each *yes* voter. The bid replaces `subagent_type` routing; worker mechanics are unchanged.
4. **Collect** — volunteers write their answer to the **response board** (`atria:bb:{run}:responses`) plus durable findings to the note channel as today. The main agent reads responses for its `request_id`.

The bid is evaluated per-profile as separate decisions — faithful to "each agent autonomously decides," without booting a full worker to say "no."

### 4. Main-agent tool surface — `task_tool.py` + registry

- `subagent(tasks=[{subagent_type, prompt}])` → **`request_help(prompt, max_helpers?)`** — no addressee. The paper's "Requesting Help" action.
- `get_subagent_output(job_id)` → **`get_help_responses(request_id)`** — returns response-board entries + note digest.

### 5. Web-ui blackboard viewer — `web-ui/src/`

A real blackboard view (extend `DispatchPage.tsx` or a new `BlackboardPage.tsx` + `solverJobs.ts`) showing, per request: the **request text**, the **bid roster** (who volunteered / declined + reason — the paper's autonomy made visible), the **response board**, and the note digest. New WS events bridged through `atria/web/blackboard_subscriber.py`: `blackboard.request`, `blackboard.bid`, `blackboard.response` (alongside existing `blackboard.note`).

### 6. Removed / out of scope

**Removed:** `subagent_type` routing from the tool, `Task.subagent_type` semantics, `TaskStore.claim`-as-routing (claim stays only as worker idempotency).

**Out of scope (future):** workspace clustering + per-cluster file agents (Approach B), dynamic profiles, admission gating on responses.

## Data flow

```
main agent
  └─ request_help(prompt)                  → Request written to atria:bb:{run}:requests   [β]
       └─ orchestrator broadcasts
            ├─ bid(Planner.profile, req)    → yes/no + reason   (independent cheap LLM)
            ├─ bid(WebGen.profile, req)     → yes/no + reason
            └─ bid(moduleWorker.profile,req)→ yes/no + reason
       └─ volunteers only → TaskIQ worker (manager.execute_subagent)
            ├─ Response → atria:bb:{run}:responses                                        [β_r]
            └─ Notes    → atria:bb:{task_id}:notes (admission-gated)                       [β]
  └─ get_help_responses(request_id)         ← responses + note digest
```

## Error handling

- **Bid failure** (LLM error/timeout): fail-closed — the helper does not volunteer. A request with zero volunteers returns an explicit "no volunteers" result so the main agent can adapt (plan, run code itself, or re-request).
- **Blackboard/redis unavailable:** existing fail-soft behavior in `Blackboard`/`BlackboardHandle` is preserved (writes return status strings, renders return `""`).
- **Worker failure:** unchanged from today (status `failed`, surfaced in collect).

## Testing

Per `CLAUDE.md`:
- **Unit tests:** new `Request`/`Response` models, the per-helper bid (fail-closed, concurrency cap, independence from other profiles), response-board store, `request_help`/`get_help_responses` tool schemas + registry routing, WS event emission.
- **Real end-to-end:** with `OPENAI_API_KEY` against the configured proxy, redis + `atria-worker` live — post a request, observe bids, volunteers respond on the response board, main agent collects. Verify the viewer renders requests/bids/responses.

## Success criteria

1. The main agent can post a request with no addressee and receive responses from self-selected helpers.
2. No code path routes work by a caller-chosen `subagent_type`.
3. Responses are stored and read from a store separate from the note channel.
4. The viewer shows the bid roster (volunteer/decline + reason) per request.
5. Unit + real e2e both pass.
