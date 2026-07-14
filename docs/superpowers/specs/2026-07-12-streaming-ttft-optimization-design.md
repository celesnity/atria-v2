# Real streaming & TTFT optimization — design

**Date:** 2026-07-12
**Branch base:** feat/rebrand-minder
**Scope:** Approach 1 (TTFT-first, minimal). Web UI is the primary target; TUI shares the loop and is affected where noted.

## Problem

Users perceive the chat as "fake streaming" with a long silence before anything appears.
Investigation shows the final assistant answer is **already** real token streaming
(SSE deltas 1:1 → `MESSAGE_CHUNK` → RAF-coalesced render). The real cost is upstream,
in the ReAct iteration:

1. **Blocking thinking round-trip.** When thinking is visible, `run_iteration`
   (`minder/core/agents/execution/react_executor/iteration.py`) makes a **separate,
   non-streamed** `call_thinking_llm` (`minder/core/agents/main_agent/llm_calls.py:32`)
   before the action call. For a reasoning model (gpt-5-mini) this pays for reasoning
   twice and adds a full round-trip before the first visible token.
2. **Optional critique round-trip.** A second blocking call
   (`_critique_and_refine_thinking`) can run after thinking.
3. **Fake thinking chunking.** `on_thinking` (`minder/web/web_ui_callback.py:453`)
   receives the completed thinking trace and manually splits it into 8-word chunks —
   synthetic, not real streaming.
4. **Late tool activity.** In `_consume_sse` (`minder/core/agents/components/api/http_client.py:504`)
   tool_call deltas are accumulated and only surfaced **after** the action call finishes,
   so module/tool activity lines appear late even though the tool name arrives early in the stream.

The observed experience: long silence → a burst of fake-chunked "thinking" → then the
real answer. That is the "fake stream" feeling plus high TTFT.

## Target model

Primary model is **gpt-5-mini** via the litellm proxy (per project memory). It is a
reasoning model that reasons internally server-side before emitting output tokens.
A separate prompted thinking call is therefore redundant.

## Goals

- **TTFT:** remove the blocking thinking + critique round-trips that precede the first token.
- **Tool/module activity:** surface as soon as the tool name is known, mid-stream.
- **No fake chunking:** stop the synthetic 8-word thinking chunking.
- **Do not regress** what already works: 1:1 content deltas, RAF coalescing, server/client
  TTFT stamping.

## Non-goals (YAGNI)

- Streaming `reasoning_content` live (Approach 2). Deferred; only viable if the proxy
  actually emits reasoning deltas, which OpenAI chat-completions typically hides.
- Auto-compaction latency tuning.
- Switching provider to the Responses API.

## Design

### Component 1 — Drop the redundant thinking/critique round-trip

**File:** `minder/core/agents/execution/react_executor/iteration.py`

- Add a setting `native_reasoning` (default **True**), read where other agent/runtime
  config is read (hierarchical config, same mechanism as the existing default-off
  latency flags).
- In `run_iteration`, guard the THINKING phase (`_get_thinking_trace`) and the
  SELF-CRITIQUE phase (the block spanning roughly lines 241–284) with
  `and not native_reasoning`. When `native_reasoning` is True, neither the thinking call
  nor the critique call runs; the single streamed action call carries the model's own
  internal reasoning.
- Leave `thinking_visible` (used to build tool schemas) unchanged — the think tool is
  already excluded from action schemas (`llm_calls.py:200`), so tool behavior is unaffected.

**Result:** TTFT for a turn = time to the first streamed token of the one action call,
with no preceding blocking LLM calls.

**TUI note:** the iteration loop is shared. With `native_reasoning=True`, the TUI also
stops showing the prompted thinking trace. Accepted for this scope (web-first, native
reasoning chosen). Can be revisited if TUI needs its own default.

### Component 2 — Early tool-call activity

**Files:** `minder/core/agents/components/api/http_client.py`,
`minder/core/agents/main_agent/llm_calls.py`,
`minder/core/agents/execution/react_executor/iteration.py`,
`minder/web/web_ui_callback.py`, `minder/web/protocol.py`

- Thread an optional `on_tool_call_start: Callable[[str], None]` through
  `stream_json` → `_consume_sse`, and add a matching parameter on `call_llm` /
  `_call_action_llm` so `iteration.py` can wire it to the UI callback (mirroring how
  `on_content_delta` is wired today).
- In the `_consume_sse` tool_calls accumulation loop: when a tool_call `index` first
  receives a non-empty `function.name`, invoke `on_tool_call_start(name)` **exactly once**
  for that index. Guard callback exceptions the same way `on_content_delta` is guarded
  (a UI failure must not kill the LLM call).
- Web callback: add `on_tool_call_pending(name)` that broadcasts a `TOOL_CALL` message
  with a `pending: true` flag carrying only the tool name (no args yet). The full
  `TOOL_CALL` event (with args) still fires later via the existing `on_tool_call` path.
- Only wire `on_tool_call_start` for callbacks that opt into streaming
  (`wants_stream_tokens`), consistent with `on_assistant_token`.

**Frontend:** `web-ui/src/stores/chat.ts` handles the `pending` `TOOL_CALL` by rendering
the module/tool activity line immediately; when the full `TOOL_CALL` (with args) arrives
for the same call id, it upgrades the same line rather than adding a duplicate.

### Component 3 — Remove fake chunking + add a lightweight indicator

**Files:** `minder/web/web_ui_callback.py`, `web-ui/src/stores/chat.ts`,
`web-ui/src/components/Chat/MessageList.tsx`

- With prompted thinking disabled, the 8-word loop in `on_thinking`
  (`web_ui_callback.py:453`) no longer runs on the hot path. Simplify it so that if it is
  still invoked (fallback / non-native path), it broadcasts the content **once** instead
  of splitting into synthetic chunks.
- Frontend: show a lightweight "Thinking…" indicator from `on_thinking_start` /
  `MESSAGE_START` until the first `MESSAGE_CHUNK` **or** the first `pending` `TOOL_CALL`.
  This fills the gap while the model reasons internally before the first token. Dismiss it
  as soon as real content or tool activity arrives.

## Data flow (web, after change)

```
query arrives
  → agent_executor stamps query_started_at
  → (auto-compact only if near context limit)
  → ONE streamed action LLM call
      → first content delta → on_assistant_token: stamp TTFT + broadcast MESSAGE_CHUNK
        (or) tool_call name known → on_tool_call_start → TOOL_CALL{pending}
  → frontend renders (RAF-coalesced content; activity line immediate)
```

No thinking or critique round-trips precede the action call.

## Testing

**Unit (`uv run pytest`):**
- `_consume_sse` fires `on_tool_call_start` exactly once per tool_call index, as soon as
  the function name first appears — driven by synthetic SSE lines (name split across
  deltas must still fire once, on first non-empty name).
- `run_iteration` does not call `call_thinking_llm` (and does not run critique) when
  `native_reasoning=True`; still calls the action LLM once.
- `native_reasoning=False` preserves the existing thinking/critique behavior.

**End-to-end (requires `OPENAI_API_KEY`, gpt-5-mini via proxy):**
- Compare server-side `TTFT …ms` log lines before/after — expect a clear drop.
- Confirm exactly one LLM call per turn (no separate thinking call in logs/debug).
- Confirm a tool-using turn shows the module/tool activity line before the action call
  completes.
- Confirm no fake 8-word thinking bursts appear in the UI.

## Rollout / risk

- `native_reasoning` defaults to True but is a single flag; set False to restore the old
  prompted-thinking path if a non-reasoning model needs it.
- Changes are additive on the streaming path (new optional callback param); the blocking
  `post_json` path is untouched.
- Main risk is the shared TUI losing its thinking display; called out above and reversible
  via the flag.
