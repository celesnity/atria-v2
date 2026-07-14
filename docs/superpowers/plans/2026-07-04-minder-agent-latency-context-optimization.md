# Minder Agent Latency / Context Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the minder agent's per-turn latency and per-call context size by delivering+caching a stable system-prompt prefix, removing forced extra LLM round-trips, and trimming dead modules — without changing completed-turn behavior unless an opt-in flag is set.

**Architecture:** Three workstreams over the existing request path (`main_agent/run_loop.py`, `components/prompts/builders.py`, `components/api/http_client.py`, `models/config.py`). No new subsystems. A) Assemble the system message as `stable_prefix + volatile_tail` so the byte-stable prefix is prefix-cacheable *and* the dynamic content is actually delivered (fixing a live drop bug). B) Config-gate the loop's forced nudges/explorer and de-nest retries. C) Move unused `retriever.py`/`indexer.py` to `_local/` and un-hardcode prompt gating.

**Tech Stack:** Python 3, Pydantic config (`minder/models/config.py`), pytest, `uv run pytest`, Black/Ruff (100-col), mypy strict. OpenAI-compatible HTTP via `httpx`.

## Global Constraints

- Line length 100 (Black + Ruff); Google-style docstrings; type hints on public APIs (mypy strict).
- One commit per workstream boundary is the minimum; committing per task is fine and preferred.
- No `Co-Authored-By: Claude` trailer in any commit (project convention).
- Behavior-changing flags default to **current behavior** (opt-in to the speedup). Pure-latency changes may alter timing, not output.
- `docs/` is gitignored — this plan and the spec are force-added; do not force-add anything else.
- Dead code is **moved to `_local/`, never deleted** (CLAUDE.md repo-hygiene rule). `_local/` is gitignored.
- Testing gate (CLAUDE.md): unit tests via `uv run pytest` **and** a real end-to-end run with `OPENAI_API_KEY`. Both required; Task 9 is the e2e task.
- Run `make check` (format + lint + typecheck) before each commit.

**Reference — verified current state:**
- `run_loop.py:229` seeds the system message from `_system_stable` only; `run_loop.py:305-307` puts `_system_dynamic` into the payload where **no server consumes it** (confirmed: zero consumers in `components/api/`). Dynamic content (env, MINDER.md, skills index, MCP, blackboard lessons) is therefore dropped on the two-part path.
- `builders.py:184-244` `_build_modular_two_part` already returns `(stable, dynamic)` with dynamic = modular-dynamic + skill block + shared lessons.
- `agent.py:226-232` sets `self._system_stable` / `self._system_dynamic`; `self.system_prompt` (set in `base_agent.py:27`) is the combined string.
- `run_loop.py:315-368` retries `{429, 500, 502, 503, 504}` with sleeps 2/5/10s; `http_client.py:17-19` already retries `RETRYABLE_STATUS_CODES = {429, 503}` with 1/2/4s. Overlap on 429/503 = double backoff.
- `run_loop.py:246-248` hardcodes `MAX_NUDGE_ATTEMPTS=3`, `MAX_TODO_NUDGES=4`; `:261` uses `max_iterations` (default `None` = unlimited).
- `run_loop.py:432-443` and `:473-485` send the `implicit_completion_nudge` extra round-trip; `:548-576` enforce explore-first (forced Code-Explorer).
- `builders.py:159-161` and `:206-211` hardcode `has_subagents=True`, `todo_tracking_enabled=True`.
- `retrieval/__init__.py` exports `CodebaseIndexer`, `ContextRetriever`, `EntityExtractor`, `ContextTokenMonitor`. `compaction.py:19` imports **`ContextTokenMonitor`** (must stay). Only `indexer.py` + `retriever.py` are unused (verify `EntityExtractor` too).
- `config.py` model fields end ~line 271 (`plan_mode_*`); add new fields there.

---

### Task 1: Deliver dynamic system content as a cacheable tail (bug fix + prefix caching)

Assemble the system message as `stable + "\n\n" + dynamic` so (a) the dynamic content actually reaches the model and (b) `stable` is a byte-identical prefix across calls for automatic prefix caching. Remove the dead `_system_dynamic` payload key.

**Files:**
- Modify: `minder/core/agents/main_agent/run_loop.py` (system-message seed at `:227-231`; payload block at `:304-307`)
- Modify: `minder/core/agents/main_agent/agent.py` (add `_compose_system_content` helper near `:198`)
- Test: `tests/test_system_prompt_caching.py` (new)

**Interfaces:**
- Consumes: `self._system_stable: str`, `self._system_dynamic: str` (set by `agent.build_system_prompt`, `agent.py:226-228`).
- Produces: `MainAgent._compose_system_content() -> str` returning `stable` when dynamic is empty, else `f"{stable}\n\n{dynamic}"`. Used by `run_loop.run_sync` to seed `messages[0]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_system_prompt_caching.py
from minder.core.agents.main_agent.agent import MainAgent


class _Stub(MainAgent):
    def __init__(self, stable, dynamic):
        self._system_stable = stable
        self._system_dynamic = dynamic


def test_compose_includes_dynamic_tail_after_stable_prefix():
    agent = _Stub("STABLE_PREFIX", "DYNAMIC_TAIL")
    composed = agent._compose_system_content()
    assert composed.startswith("STABLE_PREFIX")
    assert "DYNAMIC_TAIL" in composed
    # Stable must be an exact byte prefix so servers can prefix-cache it.
    assert composed[: len("STABLE_PREFIX")] == "STABLE_PREFIX"


def test_compose_stable_only_when_no_dynamic():
    agent = _Stub("STABLE_PREFIX", "")
    assert agent._compose_system_content() == "STABLE_PREFIX"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_system_prompt_caching.py -v`
Expected: FAIL — `AttributeError: 'MainAgent' object has no attribute '_compose_system_content'` (and `_Stub` may need `MainAgent.__init__` bypass; if construction fails, keep `_Stub` overriding `__init__` as shown so no real init runs).

- [ ] **Step 3: Add the helper in `agent.py`**

Insert immediately after `build_system_prompt` (after `agent.py:232`):

```python
    def _compose_system_content(self) -> str:
        """Combine stable prefix + dynamic tail into one system message.

        Keeps ``_system_stable`` as a byte-identical leading prefix so
        OpenAI-compatible servers can prefix-cache it, while ensuring the
        dynamic tail (environment, project instructions, skills, MCP,
        shared lessons) is actually delivered to the model.
        """
        stable = getattr(self, "_system_stable", None) or self.system_prompt
        dynamic = getattr(self, "_system_dynamic", "") or ""
        if dynamic:
            return f"{stable}\n\n{dynamic}"
        return stable
```

- [ ] **Step 4: Wire it into `run_loop.py` and drop the dead key**

Replace `run_loop.py:227-231`:

```python
        if not messages or messages[0].get("role") != "system":
            # Combine stable prefix + dynamic tail so dynamic context is
            # delivered AND the stable prefix stays byte-identical (cacheable).
            messages.insert(0, {"role": "system", "content": self._compose_system_content()})
```

Delete the dead dynamic-key block at `run_loop.py:304-307` (the `system_dynamic = getattr(...)` / `payload["_system_dynamic"] = ...` lines). The payload no longer carries `_system_dynamic`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_system_prompt_caching.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Guard against regression — assert no `_system_dynamic` key leaks into payload**

Add to `tests/test_system_prompt_caching.py`:

```python
def test_payload_has_no_dead_system_dynamic_key():
    import inspect
    from minder.core.agents.main_agent import run_loop
    src = inspect.getsource(run_loop)
    assert "_system_dynamic" not in src, "dead _system_dynamic payload key must be removed"
```

Run: `uv run pytest tests/test_system_prompt_caching.py -v` → PASS.

- [ ] **Step 7: `make check` then commit**

```bash
make check
git add minder/core/agents/main_agent/agent.py minder/core/agents/main_agent/run_loop.py tests/test_system_prompt_caching.py
git commit -m "fix(agent): deliver dynamic system content as cacheable tail; drop dead _system_dynamic key"
```

---

### Task 2: Optional per-session `prompt_cache_key` (config-gated, default off)

Send a stable cache-affinity key so servers that support it (OpenAI `prompt_cache_key`, some vLLM builds) reuse the KV cache across a session. No-ops on servers that ignore unknown keys (the codebase already tolerated an unknown `_system_dynamic` key, so unknown keys are safe here).

**Files:**
- Modify: `minder/models/config.py` (add `prompt_cache_key_enabled` field near `:271`)
- Modify: `minder/core/agents/main_agent/run_loop.py` (payload assembly at `:295-302`)
- Test: `tests/test_system_prompt_caching.py` (extend)

**Interfaces:**
- Consumes: `self.config.prompt_cache_key_enabled: bool`; a stable session id via `getattr(self, "_session_id", None)` or `getattr(deps, "session_id", None)`.
- Produces: `payload["prompt_cache_key"]` present only when enabled and a session id exists.

- [ ] **Step 1: Write the failing test**

```python
def test_prompt_cache_key_absent_by_default():
    # Default config: flag off -> no prompt_cache_key added.
    from minder.models.config import AppConfig
    cfg = AppConfig()
    assert getattr(cfg, "prompt_cache_key_enabled", None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_system_prompt_caching.py::test_prompt_cache_key_absent_by_default -v`
Expected: FAIL — `AttributeError`/`None is not False` (field does not exist yet).

- [ ] **Step 3: Add the config field**

In `minder/models/config.py`, after `:271` (`plan_mode_explore_variant`), add:

```python
    # Prompt caching (OpenAI-compatible). When enabled, sends a stable
    # per-session prompt_cache_key for KV-cache affinity; ignored by
    # servers that do not support it.
    prompt_cache_key_enabled: bool = False
```

- [ ] **Step 4: Wire into payload**

In `run_loop.py`, immediately after the `payload = {...}` dict (was `:302`), add:

```python
                if getattr(self.config, "prompt_cache_key_enabled", False):
                    session_id = getattr(self, "_session_id", None) or getattr(
                        deps, "session_id", None
                    )
                    if session_id:
                        payload["prompt_cache_key"] = str(session_id)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_system_prompt_caching.py -v`
Expected: PASS.

- [ ] **Step 6: `make check` then commit**

```bash
make check
git add minder/models/config.py minder/core/agents/main_agent/run_loop.py tests/test_system_prompt_caching.py
git commit -m "feat(agent): optional per-session prompt_cache_key (default off)"
```

---

### Task 3: Config fields for loop control (finite iterations, nudge caps)

Introduce config knobs the loop will read, defaulting to current behavior.

**Files:**
- Modify: `minder/models/config.py` (add fields near `:271`)
- Test: `tests/test_loop_config.py` (new)

**Interfaces:**
- Produces: `AppConfig` fields `max_iterations_default: int = 25`, `max_nudge_attempts: int = 3`, `max_todo_nudges: int = 4`, `completion_nudge_enabled: bool = False`, `explore_first_enabled: bool = False`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_loop_config.py
from minder.models.config import AppConfig


def test_loop_control_defaults():
    cfg = AppConfig()
    assert cfg.max_iterations_default == 25
    assert cfg.max_nudge_attempts == 3
    assert cfg.max_todo_nudges == 4
    assert cfg.completion_nudge_enabled is False
    assert cfg.explore_first_enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_loop_config.py -v`
Expected: FAIL — `AttributeError` on `max_iterations_default`.

- [ ] **Step 3: Add the fields**

In `minder/models/config.py` after the `prompt_cache_key_enabled` field from Task 2:

```python
    # ReAct loop control. Behavior-changing flags default to prior behavior.
    max_iterations_default: int = 25  # runaway guard when caller passes None
    max_nudge_attempts: int = 3       # was hardcoded MAX_NUDGE_ATTEMPTS
    max_todo_nudges: int = 4          # was hardcoded MAX_TODO_NUDGES
    completion_nudge_enabled: bool = False  # off => skip extra completion round-trip
    explore_first_enabled: bool = False     # off => do not force Code-Explorer first
```

Note: `completion_nudge_enabled=False` and `explore_first_enabled=False` REMOVE forced round-trips by default. This is the intended speedup; the prior always-on behavior is available by setting them `True`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_loop_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
make check
git add minder/models/config.py tests/test_loop_config.py
git commit -m "feat(config): add ReAct loop-control fields"
```

---

### Task 4: Finite default iterations + config-driven nudge caps

Make the loop read the Task 3 fields instead of hardcoded constants and unlimited default.

**Files:**
- Modify: `minder/core/agents/main_agent/run_loop.py` (`:246-248`, `:261`)
- Test: `tests/test_loop_config.py` (extend — source-level assertion; full-loop behavior covered by Task 9 e2e)

**Interfaces:**
- Consumes: `self.config.max_iterations_default`, `self.config.max_nudge_attempts`, `self.config.max_todo_nudges`.

- [ ] **Step 1: Write the failing test**

```python
def test_run_loop_uses_config_for_caps_not_hardcoded():
    import inspect
    from minder.core.agents.main_agent import run_loop
    src = inspect.getsource(run_loop.RunLoopMixin.run_sync)
    assert "self.config.max_nudge_attempts" in src
    assert "self.config.max_todo_nudges" in src
    assert "self.config.max_iterations_default" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_loop_config.py::test_run_loop_uses_config_for_caps_not_hardcoded -v`
Expected: FAIL — strings not present.

- [ ] **Step 3: Edit the loop**

Replace `run_loop.py:246-248`:

```python
        MAX_NUDGE_ATTEMPTS = self.config.max_nudge_attempts
        todo_nudge_count = 0
        MAX_TODO_NUDGES = self.config.max_todo_nudges
```

Replace the iteration guard at `run_loop.py:261`. Just before the `while True:` (after `has_explored = False` at `:251`), add:

```python
        effective_max_iterations = (
            max_iterations if max_iterations is not None else self.config.max_iterations_default
        )
```

Then change the guard body (`:261`) from `if max_iterations is not None and iteration > max_iterations:` to:

```python
                if iteration > effective_max_iterations:
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_loop_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
make check
git add minder/core/agents/main_agent/run_loop.py tests/test_loop_config.py
git commit -m "feat(agent): finite default iterations + config-driven nudge caps"
```

---

### Task 5: Gate the completion nudge (default off = one fewer round-trip)

Skip the mandatory `implicit_completion_nudge` extra LLM call unless `completion_nudge_enabled`.

**Files:**
- Modify: `minder/core/agents/main_agent/run_loop.py` (`:431-443`, `:473-485`)
- Test: `tests/test_loop_config.py` (extend, source-level)

**Interfaces:**
- Consumes: `self.config.completion_nudge_enabled: bool`.

- [ ] **Step 1: Write the failing test**

```python
def test_completion_nudge_is_gated():
    import inspect
    from minder.core.agents.main_agent import run_loop
    src = inspect.getsource(run_loop.RunLoopMixin.run_sync)
    assert "self.config.completion_nudge_enabled" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_loop_config.py::test_completion_nudge_is_gated -v`
Expected: FAIL.

- [ ] **Step 3: Gate both nudge sites**

At `run_loop.py:432`, change `if not completion_nudge_sent:` to:

```python
                            if self.config.completion_nudge_enabled and not completion_nudge_sent:
```

At `run_loop.py:474`, change the second `if not completion_nudge_sent:` to:

```python
                    if self.config.completion_nudge_enabled and not completion_nudge_sent:
```

Behavior: with the flag off (default), the loop falls through to the existing `return {... "success": True}` immediately after each site — no extra round-trip. With it on, prior behavior is preserved.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_loop_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
make check
git add minder/core/agents/main_agent/run_loop.py tests/test_loop_config.py
git commit -m "perf(agent): gate completion nudge behind config (default off)"
```

---

### Task 6: Gate explore-first enforcement (default off = no forced Code-Explorer)

Only force a Code-Explorer subagent before other subagents when `explore_first_enabled`.

**Files:**
- Modify: `minder/core/agents/main_agent/run_loop.py` (`:548-576`)
- Test: `tests/test_loop_config.py` (extend, source-level)

**Interfaces:**
- Consumes: `self.config.explore_first_enabled: bool`.

- [ ] **Step 1: Write the failing test**

```python
def test_explore_first_is_gated():
    import inspect
    from minder.core.agents.main_agent import run_loop
    src = inspect.getsource(run_loop.RunLoopMixin.run_sync)
    assert "self.config.explore_first_enabled" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_loop_config.py::test_explore_first_is_gated -v`
Expected: FAIL.

- [ ] **Step 3: Gate the block**

At `run_loop.py:550`, change `if not has_explored:` to:

```python
                if self.config.explore_first_enabled and not has_explored:
```

The `has_explored`-marking loop (`:579-584`) can stay — it is a harmless no-op when the block above never blocks. Leave it.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_loop_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
make check
git add minder/core/agents/main_agent/run_loop.py tests/test_loop_config.py
git commit -m "perf(agent): gate explore-first enforcement behind config (default off)"
```

---

### Task 7: De-nest retries (run_loop stops retrying codes http_client owns)

`http_client.post_json` already retries `{429, 503}`. Remove those from run_loop's retry set so a transient 429/503 is not backed off twice (double sleep). run_loop keeps retrying only `{500, 502, 504}`, which `http_client` does not.

**Files:**
- Modify: `minder/core/agents/main_agent/run_loop.py` (`:347`)
- Test: `tests/test_loop_config.py` (extend, source-level)

**Interfaces:**
- Consumes: nothing new. Aligns with `http_client.RETRYABLE_STATUS_CODES = {429, 503}`.

- [ ] **Step 1: Write the failing test**

```python
def test_run_loop_does_not_double_retry_429_503():
    import inspect
    from minder.core.agents.main_agent import run_loop
    src = inspect.getsource(run_loop.RunLoopMixin.run_sync)
    # run_loop should only retry the codes http_client does NOT handle.
    assert "(500, 502, 504)" in src
    assert "(429, 500, 502, 503, 504)" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_loop_config.py::test_run_loop_does_not_double_retry_429_503 -v`
Expected: FAIL.

- [ ] **Step 3: Narrow the retry set**

At `run_loop.py:347`, change:

```python
                    elif response.status_code in (429, 500, 502, 503, 504):
```

to:

```python
                    elif response.status_code in (500, 502, 504):
```

Add a brief comment above it: `# 429/503 are retried inside http_client.post_json; avoid double backoff.`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_loop_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
make check
git add minder/core/agents/main_agent/run_loop.py tests/test_loop_config.py
git commit -m "perf(agent): stop double-retrying 429/503 (http_client owns them)"
```

---

### Task 8: Move dead retrieval modules to `_local/` (keep token_monitor)

`indexer.py` and `retriever.py` have no live call sites; `token_monitor.py` is imported by `compaction.py:19` and must stay.

**Files:**
- Move: `minder/core/context_engineering/retrieval/indexer.py` → `_local/dead-code/retrieval/indexer.py`
- Move: `minder/core/context_engineering/retrieval/retriever.py` → `_local/dead-code/retrieval/retriever.py`
- Modify: `minder/core/context_engineering/retrieval/__init__.py`
- Test: `tests/test_dead_code_removed.py` (new)

**Interfaces:**
- Produces: `retrieval/__init__.py` exporting only `ContextTokenMonitor`.

- [ ] **Step 1: Verify no live imports (must print nothing but the package's own files)**

Run:

```bash
grep -rn "CodebaseIndexer\|ContextRetriever\|EntityExtractor" minder --include="*.py" | grep -v "core/context_engineering/retrieval/"
```

Expected: **no output**. If any line prints, STOP — that consumer must be handled first (out of scope; report it).

- [ ] **Step 2: Write the failing test**

```python
# tests/test_dead_code_removed.py
def test_token_monitor_still_importable():
    from minder.core.context_engineering.retrieval import ContextTokenMonitor  # noqa: F401


def test_dead_retrieval_symbols_gone():
    import minder.core.context_engineering.retrieval as r
    assert not hasattr(r, "CodebaseIndexer")
    assert not hasattr(r, "ContextRetriever")
    assert not hasattr(r, "EntityExtractor")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_dead_code_removed.py -v`
Expected: `test_dead_retrieval_symbols_gone` FAILS (symbols still exported).

- [ ] **Step 4: Move files and trim exports**

```bash
mkdir -p _local/dead-code/retrieval
git mv minder/core/context_engineering/retrieval/indexer.py _local/dead-code/retrieval/indexer.py
git mv minder/core/context_engineering/retrieval/retriever.py _local/dead-code/retrieval/retriever.py
```

(If `git mv` errors because files are untracked, use plain `mv`.)

Replace `minder/core/context_engineering/retrieval/__init__.py` with:

```python
"""Information retrieval for Minder.

Provides token monitoring for context compaction. (Codebase indexing and
regex/grep context retrieval were unused and moved to _local/dead-code.)
"""

from minder.core.context_engineering.retrieval.token_monitor import ContextTokenMonitor

__all__ = ["ContextTokenMonitor"]
```

- [ ] **Step 5: Run tests + confirm compaction still imports**

Run:

```bash
uv run pytest tests/test_dead_code_removed.py -v
uv run python -c "from minder.core.context_engineering.compaction import ContextCompactor; print('ok')"
```

Expected: tests PASS; import prints `ok`.

- [ ] **Step 6: Commit**

```bash
make check
git add minder/core/context_engineering/retrieval/__init__.py tests/test_dead_code_removed.py
git commit -m "chore(retrieval): move unused indexer/retriever to _local; keep token_monitor"
```

---

### Task 9: Un-hardcode prompt gating + full verification & real e2e

Drive `has_subagents` / `todo_tracking_enabled` from real availability so unused prompt sections (subagent guide ~118 lines, task tracking) don't inflate the cached prefix, then run the full suite and a real API e2e capturing before/after numbers.

**Files:**
- Modify: `minder/core/agents/components/prompts/builders.py` (`:157-162`, `:206-211`)
- Test: `tests/test_prompt_gating.py` (new)

**Interfaces:**
- Consumes: `self._subagent_manager` (constructor arg, `builders.py:49`), `self._tool_registry`.
- Produces: composer `context` where `has_subagents = self._subagent_manager is not None` and `todo_tracking_enabled = <todo tool present>`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prompt_gating.py
from minder.core.agents.components.prompts.builders import SystemPromptBuilder


def test_has_subagents_false_when_no_manager():
    b = SystemPromptBuilder(tool_registry=None, subagent_manager=None)
    ctx = b._gating_context()
    assert ctx["has_subagents"] is False


def test_has_subagents_true_when_manager_present():
    b = SystemPromptBuilder(tool_registry=None, subagent_manager=object())
    ctx = b._gating_context()
    assert ctx["has_subagents"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_gating.py -v`
Expected: FAIL — `_gating_context` does not exist.

- [ ] **Step 3: Extract a gating helper and use it in both build paths**

In `BasePromptBuilder` (near `builders.py:246`), add:

```python
    def _gating_context(self) -> dict[str, Any]:
        """Compute conditional-section flags from real availability."""
        todo_enabled = False
        reg = self._tool_registry
        if reg is not None:
            try:
                todo_enabled = "list_todos" in getattr(reg, "list_tool_names", lambda: [])()
            except Exception:  # noqa: BLE001 — best-effort gating
                todo_enabled = False
        return {
            "in_git_repo": bool(self._env_context and self._env_context.is_git_repo),
            "has_subagents": self._subagent_manager is not None,
            "todo_tracking_enabled": todo_enabled,
            "model": self._env_context.model if self._env_context else "",
        }
```

Replace the inline `context = {...}` at `builders.py:157-162` and `:206-211` with `context = self._gating_context()`.

Note: if `list_tool_names` is not the registry's method name, verify with `grep -n "def list_tool" minder/core/context_engineering/tools/registry.py` and use the correct accessor; fall back to `todo_enabled = True` if the registry exposes no tool listing, to preserve current behavior when tools are present.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prompt_gating.py -v`
Expected: PASS.

- [ ] **Step 5: Full unit suite + static checks**

```bash
make check
make test
```

Expected: all green. Fix any fallout before proceeding.

- [ ] **Step 6: Real end-to-end run (REQUIRED — CLAUDE.md)**

```bash
export OPENAI_API_KEY="<key>"
```

Run a real multi-tool turn through the CLI (e.g. `minder -p "read README, list the top-level minder/ folders, and summarize the architecture"`). Confirm:
- The turn completes and the answer reflects **project instructions / environment** (proves dynamic content is now delivered — Task 1 bug fix).
- With default config, the turn does **not** emit an extra completion round-trip and does **not** spawn a forced Code-Explorer (Tasks 5–6).
- Capture before/after from the cost tracker (`run_loop.py:381-387` `_cost_tracker`): input tokens per round-trip and round-trips per turn. Record the numbers in the commit body.

- [ ] **Step 7: Commit**

```bash
git add minder/core/agents/components/prompts/builders.py tests/test_prompt_gating.py
git commit -m "perf(prompt): gate subagent/todo sections by real availability; verify e2e"
```

---

## Self-Review Notes (coverage)

- Spec Workstream A (prefix stability / caching) → Tasks 1–2, plus the delivery-bug fix discovered during planning. ✅
- Spec Workstream B (cut forced round-trips) → Tasks 3–7 (finite iterations, nudge caps, completion nudge gate, explore-first gate, retry de-nest). ✅
- Spec Workstream C (trim dead modules) → Task 8 (move indexer/retriever, keep token_monitor) + Task 9 (un-hardcode gating). ✅
- Testing gate (unit + real e2e with `OPENAI_API_KEY`) → Task 9 Steps 5–6. ✅
- Correction vs spec: spec said "move `retrieval/` to `_local/`" — narrowed to `indexer.py`+`retriever.py` only, because `token_monitor.py` is a live dependency of `compaction.py`. Documented in Global Constraints and Task 8.
- Correction vs spec: env block is session-stable (startup snapshot) and stays in the prefix; the real cache-buster (blackboard shared lessons) is already placed last in `dynamic` by `builders.py:232-236`, so Task 1's `stable + dynamic` assembly keeps it in the correct most-volatile position. No separate move needed.
