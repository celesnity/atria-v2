import { Agent } from '../embinder';
import type { PlatformAction, PlatformState } from './types';

type EmbinderBind = { 'data-embinder-tool': string };

export function WorkflowApprovalsPage({ state, dispatch, approveBind, rejectBind }: { state: PlatformState; dispatch: (action: PlatformAction) => void; approveBind: EmbinderBind; rejectBind: EmbinderBind }) {
  const pending = state.workflow.status === 'pending_approval';
  return <div><p style={{ color: '#9ca8c8', fontSize: 12, letterSpacing: '0.1em', fontWeight: 800 }}>GATED DECISION WORKFLOW</p><h1 style={{ margin: '6px 0 8px', fontSize: 34 }}>Workflow &amp; Approvals</h1><p style={{ color: '#9ca8c8' }}>Final decisions are Embinder destructive actions. They use the direct approval gate, not MCP.</p>
    <section style={{ padding: 18, border: '1px solid #2b3758', borderRadius: 12, background: '#141b31', maxWidth: 760 }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 14 }}><div><span style={{ color: '#9ca8c8', fontSize: 12 }}>WORKFLOW {state.workflow.id}</span><h2 style={{ margin: '5px 0' }}>{state.workflow.title}</h2><p style={{ color: '#9ca8c8' }}>Owner: {state.workflow.owner} · Incident: {state.workflow.incidentId}</p></div><strong style={{ alignSelf: 'start', padding: '7px 10px', borderRadius: 999, background: pending ? '#5d4314' : '#203856', color: pending ? '#fbbf24' : '#9bc3ff' }}>{state.workflow.status.replaceAll('_', ' ')}</strong></div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 16 }}><Agent.Button name="submit_mitigation" description="Submit the selected incident mitigation proposal for human approval" onAct={() => dispatch({ type: 'submit_mitigation' })}>Submit mitigation proposal</Agent.Button>{pending ? <><Agent.Button name="approve_escalation" description="Approve the pending escalation through the Embinder approval gate" embinderBind={approveBind} onAct={() => dispatch({ type: 'approve_escalation' })}>Approve escalation</Agent.Button><Agent.Button name="reject_escalation" description="Reject the pending escalation through the Embinder approval gate" embinderBind={rejectBind} onAct={() => dispatch({ type: 'reject_escalation' })}>Reject escalation</Agent.Button></> : null}</div>
    </section>
  </div>;
}
