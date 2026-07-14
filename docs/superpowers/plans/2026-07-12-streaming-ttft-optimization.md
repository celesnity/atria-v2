# Real Streaming & TTFT Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut time-to-first-token and make tool activity appear mid-stream by removing the redundant blocking thinking/critique round-trips and surfacing tool calls as soon as their name is known.

**Architecture:** A single streamed action LLM call carries the reasoning model's own internal reasoning (no separate prompted-thinking call). The streaming SSE reader fires a callback the moment a tool_call name appears, which the web layer broadcasts as a `pending` TOOL_CALL so the UI renders the activity line immediately. Fake 8-word thinking chunking is removed and a lightweight "Thinking…" indicator fills the pre-first-token gap.

**Tech Stack:** Python 3 (agent core, FastAPI web), pytest; React/TypeScript/Zustand web-ui, vitest.

## Global Constraints

- Python line length: 100 chars (Black + Ruff). Type hints on public APIs (mypy strict). Google-style docstrings.
- Run Python tests with `uv run --no-sync pytest` (avoids re-sync churn).
- Run frontend tests with `pnpm --dir web-ui test` (vitest).
- Never hard-code if/else branching for LLM conversation flow beyond a single config gate; the model still decides tool use.
- `native_reasoning` config flag defaults to **True**.
- New streaming callbacks are wired only for callbacks that opt in via `wants_stream_tokens`, mirroring the existing `on_assistant_token` wiring.
- The blocking `post_json` path must remain untouched; all new behavior lives on the streaming path.
- Do not commit anything under `minder-home/` or `.minder/`. Spec/plan docs under `docs/` require `git add -f` (docs is gitignored).

---

### Task 1: `native_reasoning` flag — skip the blocking thinking/critique phase

**Files:**
- Modify: `minder/models/config.py` (add field after `temperature`, ~line 258)
- Modify: `minder/core/agents/execution/react_executor/iteration.py` (add module helper near line 34; gate the thinking block at ~241)
- Test: `tests/test_native_reasoning_gate.py` (create)

**Interfaces:**
- Produces: module-level function
  `_should_run_thinking(*, native_reasoning: bool, thinking_visible: bool, should_skip_thinking: bool) -> bool`
  in `iteration.py`.
- Produces: config field `AgentConfig.native_reasoning: bool = True` (read via `getattr(self.config, "native_reasoning", True)`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_native_reasoning_gate.py`:

```python
"""Unit tests for the thinking-phase gate helper."""

from minder.core.agents.execution.react_executor.iteration import _should_run_thinking


def test_native_reasoning_skips_thinking():
    # When native reasoning is on, the prompted thinking phase never runs,
    # even if thinking is visible and not otherwise skipped.
    assert _should_run_thinking(
        native_reasoning=True, thinking_visible=True, should_skip_thinking=False
    ) is False


def test_prompted_thinking_runs_when_native_off():
    assert _should_run_thinking(
        native_reasoning=False, thinking_visible=True, should_skip_thinking=False
    ) is True


def test_prompted_thinking_respects_visibility_and_skip():
    assert _should_run_thinking(
        native_reasoning=False, thinking_visible=False, should_skip_thinking=False
    ) is False
    assert _should_run_thinking(
        native_reasoning=False, thinking_visible=True, should_skip_thinking=True
    ) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_native_reasoning_gate.py -v`
Expected: FAIL with `ImportError: cannot import name '_should_run_thinking'`

- [ ] **Step 3: Add the config field**

In `minder/models/config.py`, immediately after the `temperature: float = 0.6` line (~258), add:

```python

    # Reasoning models (e.g. gpt-5-mini) reason internally during the single
    # streamed action call, so a separate prompted-thinking round-trip is
    # redundant and only adds latency before the first token. When True (default)
    # the executor skips the prompted thinking + self-critique phases. Set False
    # for non-reasoning models that need an explicit prompted thinking trace.
    native_reasoning: bool = True
```

- [ ] **Step 4: Add the helper**

In `minder/core/agents/execution/react_executor/iteration.py`, after the
`_call_llm_accepts_delta` function (~line 36), add:

```python
def _should_run_thinking(
    *, native_reasoning: bool, thinking_visible: bool, should_skip_thinking: bool
) -> bool:
    """Whether the prompted (blocking) thinking phase should run this iteration.

    Reasoning models reason inside the single streamed action call, so the
    separate prompted-thinking round-trip is skipped entirely when
    ``native_reasoning`` is set.
    """
    if native_reasoning:
        return False
    return thinking_visible and not should_skip_thinking
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/test_native_reasoning_gate.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Gate the thinking block in `_run_iteration_inner`**

In `minder/core/agents/execution/react_executor/iteration.py`, find (~line 241):

```python
        if thinking_visible and not should_skip_thinking:
            thinking_trace = self._get_thinking_trace(
```

Replace the `if` line (only the condition line) with:

```python
        self._current_thinking_trace = None
        native_reasoning = getattr(self.config, "native_reasoning", True)
        if _should_run_thinking(
            native_reasoning=native_reasoning,
            thinking_visible=thinking_visible,
            should_skip_thinking=should_skip_thinking,
        ):
            thinking_trace = self._get_thinking_trace(
```

(The body of the block — critique, trace injection — is unchanged; it is now gated by the helper.)

- [ ] **Step 7: Run the full fast suite to check nothing broke**

Run: `uv run --no-sync pytest tests/test_native_reasoning_gate.py tests/ -k "iteration or react or thinking" -v`
Expected: PASS (new tests pass; existing iteration/react tests still pass)

- [ ] **Step 8: Commit**

```bash
git add minder/models/config.py minder/core/agents/execution/react_executor/iteration.py tests/test_native_reasoning_gate.py
git commit -m "feat(agent): native_reasoning flag skips redundant thinking round-trip"
```

---

### Task 2: Fire `on_tool_call_start` from the SSE reader

**Files:**
- Modify: `minder/core/agents/components/api/http_client.py` (`stream_json` ~353, `_consume_sse` ~448)
- Test: `tests/test_stream_tool_call_start.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `HttpClient.stream_json(..., on_tool_call_start: Optional[Callable[[str, str], None]] = None)`
  and `_consume_sse(..., on_tool_call_start)`. The callback is invoked exactly once per
  tool_call index, as `(function_name, tool_call_id)`, the first time a non-empty function
  name is seen for that index.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stream_tool_call_start.py`:

```python
"""Unit tests for early tool-call notification during SSE streaming."""

import json

from minder.core.agents.components.api.http_client import HttpClient


class _FakeResponse:
    """Minimal stand-in for httpx.Response.iter_lines()."""

    def __init__(self, lines):
        self._lines = lines

    def iter_lines(self):
        yield from self._lines


def _sse(obj) -> str:
    return "data: " + json.dumps(obj)


def _delta_chunk(delta):
    return _sse({"choices": [{"delta": delta, "finish_reason": None}]})


def test_on_tool_call_start_fires_once_with_name_and_id():
    client = HttpClient.__new__(HttpClient)  # no network; call the reader directly
    started = []

    lines = [
        # opening tool_call chunk: id + function name together
        _delta_chunk(
            {"tool_calls": [{"index": 0, "id": "call_abc",
                             "type": "function",
                             "function": {"name": "read_file", "arguments": ""}}]}
        ),
        # argument fragments arrive later — must NOT fire again
        _delta_chunk(
            {"tool_calls": [{"index": 0, "function": {"arguments": "{\"path\":"}}]}
        ),
        _delta_chunk(
            {"tool_calls": [{"index": 0, "function": {"arguments": " \"a.py\"}"}}]}
        ),
        "data: [DONE]",
    ]

    result = client._consume_sse(
        _FakeResponse(lines),
        task_monitor=None,
        on_content_delta=None,
        counter={"emitted": 0},
        on_tool_call_start=lambda name, cid: started.append((name, cid)),
    )

    assert started == [("read_file", "call_abc")]
    msg = result.data["choices"][0]["message"]
    assert msg["tool_calls"][0]["function"]["name"] == "read_file"
    assert msg["tool_calls"][0]["function"]["arguments"] == '{"path": "a.py"}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_stream_tool_call_start.py -v`
Expected: FAIL with `TypeError: _consume_sse() got an unexpected keyword argument 'on_tool_call_start'`

- [ ] **Step 3: Thread the parameter through `stream_json`**

In `minder/core/agents/components/api/http_client.py`, update the `stream_json` signature (~353):

```python
    def stream_json(
        self,
        payload: dict[str, Any],
        *,
        task_monitor: Union[Any, None] = None,
        on_content_delta: Optional[Callable[[str], None]] = None,
        on_tool_call_start: Optional[Callable[[str, str], None]] = None,
    ) -> StreamResult:
```

Then update the single call site inside `stream_json` that invokes `_consume_sse` (~411):

```python
                    return self._consume_sse(
                        response, task_monitor, on_content_delta, counter,
                        on_tool_call_start=on_tool_call_start,
                    )
```

- [ ] **Step 4: Emit the callback in `_consume_sse`**

Update the `_consume_sse` signature (~448):

```python
    def _consume_sse(
        self,
        response: httpx.Response,
        task_monitor: Any,
        on_content_delta: Optional[Callable[[str], None]],
        counter: dict[str, int],
        on_tool_call_start: Optional[Callable[[str, str], None]] = None,
    ) -> StreamResult:
```

Add a tracking set just after `tool_calls_acc: dict[int, dict[str, Any]] = {}` (~458):

```python
        tool_call_started: set[int] = set()
```

Replace the tool_calls accumulation loop (~504-518) with:

```python
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                acc = tool_calls_acc.setdefault(
                    idx,
                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                )
                if tc.get("id"):
                    acc["id"] = tc["id"]
                if tc.get("type"):
                    acc["type"] = tc["type"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    acc["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    acc["function"]["arguments"] += fn["arguments"]
                # Surface the tool the moment its name is known so the UI can
                # render activity mid-stream instead of after the whole call.
                if (
                    idx not in tool_call_started
                    and acc["function"]["name"]
                    and on_tool_call_start is not None
                ):
                    tool_call_started.add(idx)
                    try:
                        on_tool_call_start(acc["function"]["name"], acc["id"])
                    except Exception:  # UI failure must not kill the LLM call
                        logger.exception("on_tool_call_start callback failed")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/test_stream_tool_call_start.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add minder/core/agents/components/api/http_client.py tests/test_stream_tool_call_start.py
git commit -m "feat(api): emit on_tool_call_start when a streamed tool name appears"
```

---

### Task 3: Wire `on_tool_call_start` end-to-end and broadcast a `pending` TOOL_CALL

**Files:**
- Modify: `minder/core/agents/main_agent/llm_calls.py` (`call_llm` ~175)
- Modify: `minder/core/agents/execution/react_executor/iteration.py` (`_call_action_llm` ~168, wiring ~341-356, add accepts-helper ~34)
- Modify: `minder/web/web_ui_callback.py` (add `on_tool_call_pending` near `on_tool_call` ~144)
- Test: `tests/test_tool_call_pending_broadcast.py` (create)

**Interfaces:**
- Consumes: `HttpClient.stream_json(..., on_tool_call_start=...)` from Task 2.
- Produces:
  - `call_llm(..., on_tool_call_start: Optional[Any] = None)` in `LlmCallsMixin`.
  - `_call_action_llm(self, agent, messages, task_monitor, thinking_visible, on_content_delta=None, on_tool_call_start=None)`.
  - `WebUICallback.on_tool_call_pending(self, tool_name: str, tool_call_id: str = "") -> None`
    which broadcasts a `TOOL_CALL` WS message with `pending: True` and empty `arguments`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tool_call_pending_broadcast.py`:

```python
"""The pending tool-call broadcast carries name + id and a pending flag."""

from minder.web.web_ui_callback import WebUICallback
from minder.web.protocol import WSMessageType


def _make_callback():
    cb = WebUICallback.__new__(WebUICallback)
    cb.session_id = "sess1"
    cb._sent = []
    cb._broadcast = lambda msg: cb._sent.append(msg)  # type: ignore[attr-defined]
    return cb


def test_on_tool_call_pending_broadcasts_pending_tool_call():
    cb = _make_callback()
    cb.on_tool_call_pending("read_file", "call_abc")

    assert len(cb._sent) == 1
    msg = cb._sent[0]
    assert msg["type"] == WSMessageType.TOOL_CALL
    data = msg["data"]
    assert data["tool_name"] == "read_file"
    assert data["tool_call_id"] == "call_abc"
    assert data["pending"] is True
    assert data["arguments"] == {}
    assert data["session_id"] == "sess1"


def test_wants_stream_tokens_enabled():
    # Regression guard: the web callback opts into streaming callbacks.
    assert WebUICallback.wants_stream_tokens is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_tool_call_pending_broadcast.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'on_tool_call_pending'`

- [ ] **Step 3: Add `on_tool_call_pending` to the web callback**

In `minder/web/web_ui_callback.py`, directly after the `on_tool_call` method (~148), add:

```python
    def on_tool_call_pending(self, tool_name: str, tool_call_id: str = "") -> None:
        """Announce a tool call the instant its name is known during streaming.

        Fires from the SSE reader before the action call completes, so the UI
        renders the activity line immediately. The full ``tool_call`` event
        (with arguments) arrives later via WebSocketToolBroadcaster and upgrades
        the same line, matched by ``tool_call_id``.
        """
        self._broadcast(
            {
                "type": WSMessageType.TOOL_CALL,
                "data": {
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "arguments": {},
                    "arguments_display": None,
                    "description": f"Calling {tool_name}",
                    "pending": True,
                    "session_id": self.session_id,
                },
            }
        )
```

- [ ] **Step 4: Run the web-callback test to verify it passes**

Run: `uv run --no-sync pytest tests/test_tool_call_pending_broadcast.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Add `on_tool_call_start` to `call_llm`**

In `minder/core/agents/main_agent/llm_calls.py`, update the `call_llm` signature (~175):

```python
    def call_llm(
        self,
        messages: list[dict],
        task_monitor: Optional[Any] = None,
        thinking_visible: bool = True,
        on_content_delta: Optional[Any] = None,
        on_tool_call_start: Optional[Any] = None,
    ) -> dict:
```

Then update the `stream_json` call (~228) to forward it:

```python
                stream = http_client.stream_json(
                    payload,
                    task_monitor=task_monitor,
                    on_content_delta=on_content_delta,
                    on_tool_call_start=on_tool_call_start,
                )
```

- [ ] **Step 6: Add an accepts-helper and thread through `_call_action_llm`**

In `minder/core/agents/execution/react_executor/iteration.py`, after
`_call_llm_accepts_delta` (~36), add:

```python
def _call_llm_accepts_tool_start(bound_method: Callable) -> bool:
    """Signature check for a (possibly bound) ``call_llm`` accepting on_tool_call_start."""
    func = getattr(bound_method, "__func__", bound_method)
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False
    if "on_tool_call_start" in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
```

Update `_call_action_llm` (~168) to accept and forward the callback:

```python
    def _call_action_llm(
        self, agent, messages, task_monitor, thinking_visible,
        on_content_delta=None, on_tool_call_start=None,
    ):
        """Call LLM for action phase. Uses llm_caller if available (TUI spinner), otherwise direct.

        Returns:
            Tuple of (response_dict, latency_ms)
        """
        if self._llm_caller:
            # TUI path renders whole messages; token streaming is web-only.
            return self._llm_caller.call_llm_with_progress(
                agent, messages, task_monitor, thinking_visible=thinking_visible
            )
        import time

        kwargs = {}
        if on_content_delta is not None and _call_llm_accepts_delta(agent.call_llm):
            kwargs["on_content_delta"] = on_content_delta
        if on_tool_call_start is not None and _call_llm_accepts_tool_start(agent.call_llm):
            kwargs["on_tool_call_start"] = on_tool_call_start
        start = time.monotonic()
        response = agent.call_llm(
            messages, task_monitor=task_monitor, thinking_visible=thinking_visible, **kwargs
        )
        latency = int((time.monotonic() - start) * 1000)
        return response, latency
```

- [ ] **Step 7: Wire the callback in `_run_iteration_inner`**

In `minder/core/agents/execution/react_executor/iteration.py`, find the
`on_content_delta` wiring block (~341-348) and, immediately after it, add the
tool-start wiring; then pass it into `_call_action_llm` (~350-356):

```python
        on_content_delta = None
        _cb = ctx.ui_callback
        if (
            _cb is not None
            and getattr(_cb, "wants_stream_tokens", False)
            and hasattr(_cb, "on_assistant_token")
        ):
            on_content_delta = _cb.on_assistant_token

        on_tool_call_start = None
        if (
            _cb is not None
            and getattr(_cb, "wants_stream_tokens", False)
            and hasattr(_cb, "on_tool_call_pending")
        ):
            on_tool_call_start = _cb.on_tool_call_pending

        response, latency_ms = self._call_action_llm(
            ctx.agent,
            ctx.messages,
            task_monitor,
            thinking_visible=thinking_visible,
            on_content_delta=on_content_delta,
            on_tool_call_start=on_tool_call_start,
        )
```

- [ ] **Step 8: Run tests to verify nothing broke**

Run: `uv run --no-sync pytest tests/test_tool_call_pending_broadcast.py tests/test_stream_tool_call_start.py tests/ -k "llm or iteration or react" -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add minder/core/agents/main_agent/llm_calls.py minder/core/agents/execution/react_executor/iteration.py minder/web/web_ui_callback.py tests/test_tool_call_pending_broadcast.py
git commit -m "feat(web): broadcast pending tool_call the moment its name streams in"
```

---

### Task 4: Frontend — upsert tool_call by id so pending + full merge

**Files:**
- Create: `web-ui/src/utils/toolCalls.ts`
- Modify: `web-ui/src/stores/chat.ts` (`wsClient.on('tool_call', ...)` ~782-801)
- Test: `web-ui/src/utils/toolCalls.test.ts` (create)

**Interfaces:**
- Consumes: the `pending: true` TOOL_CALL payload from Task 3 and the existing full TOOL_CALL payload from `ws_tool_broadcaster.py`.
- Produces: `upsertToolCall(messages: Message[], data: any): Message[]` — appends a new
  `tool_call` message, or, when a message with the same non-empty `tool_call_id` already
  exists, merges the new fields into it (later full payload wins over the earlier pending one).

- [ ] **Step 1: Write the failing test**

Create `web-ui/src/utils/toolCalls.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { upsertToolCall } from './toolCalls';

const pending = {
  tool_call_id: 'call_abc',
  tool_name: 'read_file',
  arguments: {},
  arguments_display: null,
  description: 'Calling read_file',
  pending: true,
};

const full = {
  tool_call_id: 'call_abc',
  tool_name: 'read_file',
  arguments: { path: 'a.py' },
  arguments_display: 'path=a.py',
  description: 'Calling read_file',
  activity: { running: 'Reading…', done: 'Read' },
};

describe('upsertToolCall', () => {
  it('appends a pending tool_call as a new message', () => {
    const out = upsertToolCall([], pending);
    expect(out).toHaveLength(1);
    expect(out[0].role).toBe('tool_call');
    expect(out[0].tool_call_id).toBe('call_abc');
    expect(out[0].tool_name).toBe('read_file');
  });

  it('upgrades the pending message in place when the full call arrives', () => {
    const afterPending = upsertToolCall([], pending);
    const afterFull = upsertToolCall(afterPending, full);
    expect(afterFull).toHaveLength(1); // no duplicate
    expect(afterFull[0].tool_args).toEqual({ path: 'a.py' });
    expect(afterFull[0].tool_args_display).toBe('path=a.py');
    expect(afterFull[0].activity).toEqual({ running: 'Reading…', done: 'Read' });
  });

  it('appends separate messages when ids differ', () => {
    const out = upsertToolCall(upsertToolCall([], pending), { ...full, tool_call_id: 'call_xyz' });
    expect(out).toHaveLength(2);
  });

  it('appends when the incoming id is empty (no false merge)', () => {
    const out = upsertToolCall(upsertToolCall([], { ...pending, tool_call_id: '' }),
                               { ...pending, tool_call_id: '' });
    expect(out).toHaveLength(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir web-ui test -- toolCalls`
Expected: FAIL — cannot find module `./toolCalls`.

- [ ] **Step 3: Implement `upsertToolCall`**

Create `web-ui/src/utils/toolCalls.ts`:

```typescript
import type { Message } from '../types';

/**
 * Insert or merge a tool_call WS payload into a message list.
 *
 * A `pending` TOOL_CALL (name known, arguments not yet) arrives first from the
 * SSE reader; the full TOOL_CALL (with arguments) arrives later. Both carry the
 * same `tool_call_id`, so the later one upgrades the earlier message in place
 * instead of creating a duplicate. Empty ids never merge.
 */
export function upsertToolCall(messages: Message[], data: any): Message[] {
  const built: Message = {
    role: 'tool_call',
    content: data.description || `Calling ${data.tool_name}`,
    tool_call_id: data.tool_call_id,
    tool_name: data.tool_name,
    tool_args: data.arguments,
    tool_args_display: data.arguments_display || null,
    activity: data.activity || null,
    timestamp: new Date().toISOString(),
  };

  const id = data.tool_call_id;
  if (id) {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === 'tool_call' && m.tool_call_id === id && !m.tool_result) {
        const next = [...messages];
        // Later payload wins for args/display/activity; keep the earliest timestamp.
        next[i] = { ...m, ...built, timestamp: m.timestamp };
        return next;
      }
    }
  }
  return [...messages, built];
}
```

- [ ] **Step 4: Use it in the store handler**

In `web-ui/src/stores/chat.ts`, add the import at the top with the other util imports:

```typescript
import { upsertToolCall } from '../utils/toolCalls';
```

Replace the `wsClient.on('tool_call', ...)` handler body (~782-801) with:

```typescript
wsClient.on('tool_call', (message) => {
  const sid = resolveSessionId(message.data);
  if (!sid) return;

  useChatStore.setState(state => {
    const sessionState = getSessionState(state.sessionStates, sid);
    return patchSession(state, sid, {
      messages: upsertToolCall(sessionState.messages, message.data),
    });
  });
});
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm --dir web-ui test -- toolCalls`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add web-ui/src/utils/toolCalls.ts web-ui/src/utils/toolCalls.test.ts web-ui/src/stores/chat.ts
git commit -m "feat(web-ui): merge pending + full tool_call events by id"
```

---

### Task 5: Remove the fake 8-word thinking chunking

**Files:**
- Modify: `minder/web/web_ui_callback.py` (`on_thinking` ~453-479)
- Test: `tests/test_on_thinking_single_broadcast.py` (create)

**Interfaces:**
- Produces: `on_thinking` emits exactly one `THINKING_TOKEN` (full content) followed by one
  `THINKING_DONE`, instead of N synthetic 8-word chunks.

- [ ] **Step 1: Write the failing test**

Create `tests/test_on_thinking_single_broadcast.py`:

```python
"""on_thinking must not synthesize word-chunks; one token then done."""

from minder.web.web_ui_callback import WebUICallback
from minder.web.protocol import WSMessageType


def _make_callback():
    cb = WebUICallback.__new__(WebUICallback)
    cb.session_id = "sess1"
    cb._sent = []
    cb._broadcast = lambda msg: cb._sent.append(msg)  # type: ignore[attr-defined]
    return cb


def test_on_thinking_emits_single_token_then_done():
    cb = _make_callback()
    content = " ".join(f"word{i}" for i in range(30))  # 30 words, >8

    cb.on_thinking(content)

    tokens = [m for m in cb._sent if m["type"] == WSMessageType.THINKING_TOKEN]
    dones = [m for m in cb._sent if m["type"] == WSMessageType.THINKING_DONE]
    assert len(tokens) == 1
    assert tokens[0]["data"]["token"] == content
    assert len(dones) == 1


def test_on_thinking_ignores_empty():
    cb = _make_callback()
    cb.on_thinking("   ")
    assert cb._sent == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_on_thinking_single_broadcast.py -v`
Expected: FAIL — `test_on_thinking_emits_single_token_then_done` asserts 1 token but the 8-word loop emits 4.

- [ ] **Step 3: Replace the chunking loop**

In `minder/web/web_ui_callback.py`, replace the body of `on_thinking` (~453-479) with:

```python
    def on_thinking(self, content: str) -> None:
        """Stream a thinking trace to the UI as one block, then signal completion.

        Fallback path only: with native_reasoning on, the prompted thinking phase
        does not run. When it does run (non-reasoning models), the full trace is
        sent as a single token — no synthetic word-chunking.
        """
        if not content or not content.strip():
            return
        content = content.strip()
        self._broadcast(
            {
                "type": WSMessageType.THINKING_TOKEN,
                "data": {
                    "token": content,
                    "session_id": self.session_id,
                },
            }
        )
        self._broadcast(
            {
                "type": WSMessageType.THINKING_DONE,
                "data": {"session_id": self.session_id},
            }
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/test_on_thinking_single_broadcast.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add minder/web/web_ui_callback.py tests/test_on_thinking_single_broadcast.py
git commit -m "refactor(web): send thinking trace as one block, drop fake chunking"
```

---

### Task 6: Frontend — "Thinking…" indicator until the first token or tool activity

**Files:**
- Create: `web-ui/src/utils/thinkingIndicator.ts`
- Modify: `web-ui/src/stores/chat.ts` (set on `on_thinking_start`/`message_start`; clear on first `message_chunk` / `tool_call`)
- Modify: `web-ui/src/components/Chat/MessageList.tsx` (render the indicator)
- Test: `web-ui/src/utils/thinkingIndicator.test.ts` (create)

**Interfaces:**
- Consumes: nothing new; reacts to existing WS events.
- Produces: `nextIndicatorState(current: boolean, event: 'start' | 'chunk' | 'tool' | 'complete'): boolean`
  — pure reducer for whether the "Thinking…" indicator is visible.

- [ ] **Step 1: Write the failing test**

Create `web-ui/src/utils/thinkingIndicator.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { nextIndicatorState } from './thinkingIndicator';

describe('nextIndicatorState', () => {
  it('turns on when a turn starts', () => {
    expect(nextIndicatorState(false, 'start')).toBe(true);
  });
  it('turns off on the first streamed chunk', () => {
    expect(nextIndicatorState(true, 'chunk')).toBe(false);
  });
  it('turns off when tool activity arrives', () => {
    expect(nextIndicatorState(true, 'tool')).toBe(false);
  });
  it('turns off when the turn completes', () => {
    expect(nextIndicatorState(true, 'complete')).toBe(false);
  });
  it('stays off once cleared until the next start', () => {
    expect(nextIndicatorState(false, 'chunk')).toBe(false);
    expect(nextIndicatorState(false, 'tool')).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir web-ui test -- thinkingIndicator`
Expected: FAIL — cannot find module `./thinkingIndicator`.

- [ ] **Step 3: Implement the reducer**

Create `web-ui/src/utils/thinkingIndicator.ts`:

```typescript
/**
 * Pure reducer for the "Thinking…" indicator shown between turn start and the
 * first visible output (streamed token or tool activity). Fills the gap while a
 * reasoning model thinks internally before emitting its first token.
 */
export function nextIndicatorState(
  current: boolean,
  event: 'start' | 'chunk' | 'tool' | 'complete',
): boolean {
  switch (event) {
    case 'start':
      return true;
    case 'chunk':
    case 'tool':
    case 'complete':
      return false;
    default:
      return current;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir web-ui test -- thinkingIndicator`
Expected: PASS (5 tests)

- [ ] **Step 5: Wire indicator state into the chat store**

In `web-ui/src/stores/chat.ts`:

Add the import near the other util imports:

```typescript
import { nextIndicatorState } from '../utils/thinkingIndicator';
```

Add `thinkingIndicator: boolean` to the per-session state shape. Find the session
state initializer (the object created by `getSessionState`/the session defaults where
`pendingApproval: null` etc. are set, ~line 17) and add:

```typescript
  thinkingIndicator: false,
```

In `wsClient.on('message_start', ...)` (~565), inside the `setState`, set the flag on:

```typescript
    // existing message_start body …
    // add to the patchSession payload:
    thinkingIndicator: nextIndicatorState(false, 'start'),
```

In the `message_chunk` handler (~645), after the buffer is updated, clear it:

```typescript
  useChatStore.setState(state => {
    const s = getSessionState(state.sessionStates, sid);
    if (!s.thinkingIndicator) return {};
    return patchSession(state, sid, { thinkingIndicator: nextIndicatorState(s.thinkingIndicator, 'chunk') });
  });
```

In the `wsClient.on('tool_call', ...)` handler from Task 4, extend the patch to also clear it:

```typescript
    return patchSession(state, sid, {
      messages: upsertToolCall(sessionState.messages, message.data),
      thinkingIndicator: nextIndicatorState(sessionState.thinkingIndicator, 'tool'),
    });
```

In the `message_complete` handler (~714), clear it as a safety net:

```typescript
      thinkingIndicator: nextIndicatorState(sessionState.thinkingIndicator, 'complete'),
```

- [ ] **Step 6: Render the indicator**

In `web-ui/src/components/Chat/MessageList.tsx`, read `thinkingIndicator` from the active
session state and render a small line just below the last message when true. Near the end
of the message map, before the closing container, add:

```tsx
{thinkingIndicator && (
  <div className="flex items-center gap-2 px-3 py-1 text-xs text-slate-400">
    <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" />
    Thinking…
  </div>
)}
```

Wire `thinkingIndicator` from the store where the component already selects session state
(follow the existing `useChatStore` selector pattern in this file — the same selector that
provides `messages`).

- [ ] **Step 7: Run the frontend suite**

Run: `pnpm --dir web-ui test`
Expected: PASS (all suites, including the two new util tests)

- [ ] **Step 8: Build the UI to catch type errors**

Run: `pnpm --dir web-ui build`
Expected: build succeeds (no TS errors from the new `Message`/session fields).

- [ ] **Step 9: Commit**

```bash
git add web-ui/src/utils/thinkingIndicator.ts web-ui/src/utils/thinkingIndicator.test.ts web-ui/src/stores/chat.ts web-ui/src/components/Chat/MessageList.tsx
git commit -m "feat(web-ui): Thinking… indicator until first token or tool activity"
```

---

### Task 7: End-to-end verification with the real model

**Files:** none (verification only).

**Interfaces:** exercises the whole streaming path against gpt-5-mini via the litellm proxy.

- [ ] **Step 1: Run the full Python suite**

Run: `OPENAI_API_KEY="$OPENAI_API_KEY" uv run --no-sync pytest tests/ -q`
Expected: PASS (no regressions).

- [ ] **Step 2: Run the full frontend suite**

Run: `pnpm --dir web-ui test`
Expected: PASS.

- [ ] **Step 3: Launch the web UI**

Run: `make run` (or `minder run ui`), open the browser UI, and send a prompt that needs a
tool (e.g. "list the files in this repo and summarize the README").

- [ ] **Step 4: Observe TTFT and single-call behavior**

Watch the server log for `TTFT …ms session=…`. Confirm:
- Only one `llm_call_start` per turn (no separate thinking call) — grep the debug log.
- The `TTFT …ms` value is materially lower than before this change (compare against a
  pre-change run on the same prompt/model).

Run (in a second shell, to confirm no separate thinking round-trip):
`grep -c "llm_call_start" <session debug log>` should equal the number of ReAct
iterations, not 2× or 3× it.

- [ ] **Step 5: Observe UI behavior**

Confirm in the browser:
- A "Thinking…" indicator appears immediately, then disappears at the first token/tool line.
- The tool/module activity line appears **before** the assistant's text finishes streaming.
- No burst of 8-word "thinking" chunks.
- The final answer still streams smoothly token-by-token.

- [ ] **Step 6: Record results**

Note the before/after server TTFT numbers in the PR description. If TTFT did not drop,
STOP and debug — the thinking phase may still be running (check `native_reasoning` is
True in the effective config via `/models` or settings).

---

## Self-Review Notes

- **Spec coverage:** Component 1 → Task 1; Component 2 → Tasks 2, 3 (backend) + Task 4 (frontend); Component 3 → Task 5 (kill fake chunking) + Task 6 (indicator); Testing section → per-task unit tests + Task 7 e2e. All spec sections mapped.
- **Type consistency:** `on_tool_call_start(name, tool_call_id)` used identically in Tasks 2, 3; `on_tool_call_pending(tool_name, tool_call_id)` defined in Task 3 and wired in Task 3 Step 7; `upsertToolCall` and `nextIndicatorState` signatures match their tests.
- **Config:** `native_reasoning` read via `getattr(self.config, "native_reasoning", True)` so behavior is correct even before the field loads; field added in Task 1 Step 3 enables settings.json/env override.
