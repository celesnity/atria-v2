import { describe, expect, it } from 'vitest';
import { initialPlatformState, platformReducer, summarizePlatform } from './store';

describe('platformReducer', () => {
  it('records analysis and lowers risk for the selected incident', () => {
    const state = platformReducer(initialPlatformState, { type: 'analyze_incident' });

    expect(state.incidents[0].risk).toBe(41);
    expect(state.audit.at(-1)).toMatchObject({ action: 'analyze_incident', status: 'succeeded' });
  });

  it('requires a submitted proposal before escalation approval', () => {
    expect(() => platformReducer(initialPlatformState, { type: 'approve_escalation' })).toThrow('proposal_not_pending');
  });

  it('summarizes only the agent-relevant state', () => {
    expect(summarizePlatform(initialPlatformState)).toEqual({
      selectedIncidentId: 'INC-001',
      risk: 72,
      workflowStatus: 'draft',
      agentStatus: 'monitoring',
      auditCount: 1,
    });
  });
});
