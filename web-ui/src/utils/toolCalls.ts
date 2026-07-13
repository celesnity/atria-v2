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
