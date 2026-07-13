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
