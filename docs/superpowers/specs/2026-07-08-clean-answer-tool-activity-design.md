# Clean Answer Tool Activity Design

## Summary

User-facing assistant answers must read like normal prose. Internal retrieval modes,
command prefixes, raw stdout/stderr, and fake labels such as `grep>` must not appear
inside the assistant answer bubble unless the user explicitly asks for raw output.

Tool transparency remains visible through a separate expandable activity area for the
turn. The activity area should show what the agent did, such as searching knowledge,
reading files, or running scripts, without polluting the final answer.

## Context

The current web backend already broadcasts tool execution separately from assistant
text through `tool_call` and `tool_result` WebSocket events in
`minder/web/ws_tool_broadcaster.py`. The frontend already models those events as
separate message roles and renders them through the chat activity path in
`web-ui/src/components/Chat/MessageList.tsx` and
`web-ui/src/lib/activityGroups.ts`.

The screenshot that motivated this design shows `grep>` lines inside the assistant
answer itself. That is answer-style leakage, not the desired activity UI. The answer
should be clean; the tool trail should be adjacent, collapsible, and inspectable.

Enterprise Knowledge questions add one important constraint: the agent must continue
to use `modules/enterprise_knowledge/scripts/knowledge.py` with a `user_id`, respect
RBAC, cite claims from returned hits, and answer in Vietnamese. This design changes
presentation, not the retrieval or access-control contract.

## Goals

- Keep final answers clean, natural, and written in the user's language.
- Show agent tool usage in a separate expandable activity area.
- Make it clear whether the agent searched files, queried Enterprise Knowledge, ran
  scripts, or used other tools.
- Keep raw command output available only inside details views where it is explicitly
  inspected.
- Reuse the existing WebSocket and frontend activity architecture.
- Add guardrails so the model does not invent tool-mode labels inside final prose.

## Non-goals

- Do not hide tool usage entirely.
- Do not replace the existing `tool_call` and `tool_result` event pipeline.
- Do not implement UI-only stripping as the main fix.
- Do not weaken Enterprise Knowledge RBAC, citations, or audit behavior.
- Do not change how users explicitly request raw command output; that path may still
  show raw output when it is the requested result.

## User Experience

Each agent turn has two layers:

1. The assistant answer bubble.
2. A nearby expandable activity area for the same turn.

The assistant answer bubble contains only the answer. For an Enterprise Knowledge
question, it should use normal Vietnamese prose and citations. It should not contain
labels such as `grep>`, `dense>`, `bm25>`, command echoes, stdout dumps, stderr dumps,
or internal routing notes.

The activity area is collapsed by default in simple mode. Its collapsed header should
summarize the work in compact language, for example:

- `Activity: queried knowledge base`
- `Activity: searched files, read 3 files`
- `Activity: ran 1 script, read 2 files`

When expanded, each step shows a friendly tool label, compact arguments, status, and
short result summary. Raw output is hidden behind a deeper details affordance.

For Enterprise Knowledge, the activity label should be user-oriented, such as
`Tra cuu kho tri thuc` or `Enterprise knowledge retrieval`, instead of exposing the
raw command as the primary label. The raw command may remain available in details.

## Architecture

The implementation should keep the current separation of concerns:

- Backend: continue broadcasting `tool_call` before execution and `tool_result` after
  execution.
- Frontend store: continue storing tool events as `tool_call` messages with attached
  results.
- Activity grouping: continue folding consecutive tool/thinking/search messages into
  activity groups.
- Assistant text: render only assistant message content through the Markdown path.

The primary changes should be:

- Add or tighten prompt/skill guardrails so final assistant messages never expose
  internal retrieval prefixes, fake grep labels, or raw tool output unless requested.
- Improve activity labeling for module-script command calls, especially Enterprise
  Knowledge retrieval, so users can understand what happened without reading shell
  syntax.
- Ensure activity result summaries are concise and raw stdout/stderr remain in
  expandable details.

## Data Flow

1. The agent decides it needs a tool, such as file search, bash, or Enterprise
   Knowledge retrieval.
2. The backend broadcasts a `tool_call` event with tool name, arguments, friendly
   display text, and optional activity labels.
3. The tool runs.
4. The backend broadcasts a `tool_result` event with success, summary, raw result, and
   output.
5. The frontend attaches the result to the matching `tool_call` message.
6. The activity renderer shows the tool trail in a collapsed or expanded activity
   area.
7. The assistant final answer is streamed and rendered separately as normal prose.

## Error Handling

If a tool fails, the activity area should show a concise failure state. The assistant
answer should summarize the user-relevant effect of the failure, such as inability to
retrieve the requested knowledge, without dumping stderr by default.

If Enterprise Knowledge retrieval returns no accessible result, the answer should say
the information was not found in the user's accessible knowledge and preserve the
module's advisory note. It must not fall back to general knowledge or another user's
scope.

If raw output is explicitly requested by the user, the assistant may include it, but
the default behavior remains clean prose plus expandable activity.

## Testing

Backend and prompt-level tests should verify that the relevant guidance exists for
clean final answers and Enterprise Knowledge presentation.

Frontend tests should verify that:

- Tool calls remain separate from assistant messages.
- Consecutive tool activity can be grouped and collapsed.
- Activity summaries distinguish reads, commands, and other tool usage.
- Module-script activity labels are displayed when provided.

Regression coverage should include a fixture or assertion for the unwanted style:
assistant final answer content must not include `grep>` for a normal Enterprise
Knowledge answer.

## Acceptance Criteria

- A user can tell whether the agent used tools through the expandable activity area.
- The final assistant answer does not contain `grep>` or similar internal tool-mode
  labels for normal answers.
- Enterprise Knowledge answers remain permission-aware, cited, and in Vietnamese.
- Raw stdout/stderr are available only in details views unless explicitly requested.
- The implementation reuses existing activity/tool event architecture instead of
  adding a parallel tool telemetry channel.
