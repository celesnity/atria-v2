import type { AuditEntry, PlatformAction, PlatformState, PlatformSummary } from './types';

const baseAudit: AuditEntry[] = [
  {
    id: 'audit-001',
    at: '2026-07-20T08:00:00.000Z',
    actor: 'system',
    action: 'incident_detected',
    status: 'succeeded',
    detail: 'INC-001 traffic anomaly detected and assigned to Minder.',
  },
];

export const initialPlatformState: PlatformState = {
  incidents: [
    {
      id: 'INC-001',
      title: 'Traffic anomaly',
      risk: 72,
      status: 'investigating',
      confidence: 62,
      affectedServices: ['Edge gateway', 'Inference API'],
    },
    {
      id: 'INC-002',
      title: 'Latency regression',
      risk: 34,
      status: 'triage',
      confidence: 81,
      affectedServices: ['Customer API'],
    },
  ],
  selectedIncidentId: 'INC-001',
  workflow: {
    id: 'WF-001',
    incidentId: 'INC-001',
    title: 'Traffic isolation mitigation',
    status: 'draft',
    owner: 'Minder',
  },
  agentStatus: 'monitoring',
  audit: baseAudit,
};

function appendAudit(
  state: PlatformState,
  action: string,
  status: AuditEntry['status'],
  detail: string,
  correlationId?: string,
): AuditEntry[] {
  const entry: AuditEntry = {
    id: `audit-${String(state.audit.length + 1).padStart(3, '0')}`,
    at: `2026-07-20T08:${String(state.audit.length).padStart(2, '0')}:00.000Z`,
    actor: 'agent',
    action,
    status,
    detail,
    correlationId,
  };
  return [...state.audit, entry];
}

function selectedIndex(state: PlatformState): number {
  return state.incidents.findIndex((incident) => incident.id === state.selectedIncidentId);
}

function updateSelected(state: PlatformState, update: Partial<PlatformState['incidents'][number]>): PlatformState['incidents'] {
  const index = selectedIndex(state);
  if (index < 0) throw new Error('selected_incident_not_found');
  return state.incidents.map((incident, incidentIndex) =>
    incidentIndex === index ? { ...incident, ...update } : incident,
  );
}

export function platformReducer(state: PlatformState, action: PlatformAction): PlatformState {
  switch (action.type) {
    case 'select_incident': {
      if (!state.incidents.some((incident) => incident.id === action.incidentId)) {
        throw new Error('incident_not_found');
      }
      return {
        ...state,
        selectedIncidentId: action.incidentId,
        audit: appendAudit(state, 'select_incident', 'succeeded', `Selected ${action.incidentId}.`),
      };
    }
    case 'analyze_incident':
      return {
        ...state,
        incidents: updateSelected(state, { risk: 41, confidence: 89 }),
        agentStatus: 'analyzing',
        audit: appendAudit(state, 'analyze_incident', 'succeeded', 'Traffic anomaly isolated; risk reduced to 41.'),
      };
    case 'move_incident_triage':
      return {
        ...state,
        incidents: updateSelected(state, { status: 'triage' }),
        audit: appendAudit(state, 'move_incident_triage', 'succeeded', 'Selected incident moved to triage.'),
      };
    case 'submit_mitigation':
      return {
        ...state,
        workflow: { ...state.workflow, status: 'pending_approval' },
        agentStatus: 'awaiting_approval',
        audit: appendAudit(state, 'submit_mitigation', 'pending', 'Mitigation proposal submitted for approval.'),
      };
    case 'approve_escalation':
      if (state.workflow.status !== 'pending_approval') throw new Error('proposal_not_pending');
      return {
        ...state,
        incidents: updateSelected(state, { status: 'mitigating' }),
        workflow: { ...state.workflow, status: 'approved' },
        agentStatus: 'complete',
        audit: appendAudit(state, 'approve_escalation', 'succeeded', 'Escalation approved and mitigation started.', action.correlationId),
      };
    case 'reject_escalation':
      if (state.workflow.status !== 'pending_approval') throw new Error('proposal_not_pending');
      return {
        ...state,
        workflow: { ...state.workflow, status: 'rejected' },
        agentStatus: 'monitoring',
        audit: appendAudit(state, 'reject_escalation', 'succeeded', 'Escalation rejected; monitoring continues.', action.correlationId),
      };
    case 'reset_platform':
      return initialPlatformState;
  }
}

export function summarizePlatform(state: PlatformState): PlatformSummary {
  const incident = state.incidents.find((item) => item.id === state.selectedIncidentId);
  if (!incident) throw new Error('selected_incident_not_found');
  return {
    selectedIncidentId: incident.id,
    risk: incident.risk,
    workflowStatus: state.workflow.status,
    agentStatus: state.agentStatus,
    auditCount: state.audit.length,
  };
}
