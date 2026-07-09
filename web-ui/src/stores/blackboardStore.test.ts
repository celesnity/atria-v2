import { describe, expect, it, beforeEach } from 'vitest';
import { useBlackboardStore, __handleBoardEvent } from './blackboardStore';

describe('blackboardStore', () => {
  beforeEach(() => useBlackboardStore.getState().clear());

  it('adds a request, then bids, then responses', () => {
    __handleBoardEvent('blackboard.request', { id: 'sa_1', prompt: 'find parser', ts: 1 });
    __handleBoardEvent('blackboard.bid',
      { request_id: 'sa_1', responder: 'Planner', volunteered: true, reason: 'ok', confidence: 0.9 });
    __handleBoardEvent('blackboard.bid',
      { request_id: 'sa_1', responder: 'Web-Generator', volunteered: false, reason: 'n/a', confidence: 0 });
    __handleBoardEvent('blackboard.response',
      { request_id: 'sa_1', responder: 'Planner', content: 'parser.py:1', confidence: 0.9 });

    const req = useBlackboardStore.getState().requests['sa_1'];
    expect(req.prompt).toBe('find parser');
    expect(req.bids.length).toBe(2);
    expect(req.bids.filter((b) => b.volunteered).length).toBe(1);
    expect(req.responses[0].content).toBe('parser.py:1');
  });
});
