export type PlatformPage =
  | 'mission-control'
  | 'incident-analyst'
  | 'workflow-approvals'
  | 'activity-audit';

export type IncidentStatus = 'investigating' | 'triage' | 'mitigating' | 'resolved';
export type WorkflowStatus = 'draft' | 'pending_approval' | 'approved' | 'rejected';

export interface Incident {
  id: string;
  title: string;
  risk: number;
  status: IncidentStatus;
  confidence: number;
  affectedServices: string[];
}

export interface Workflow {
  id: string;
  incidentId: string;
  title: string;
  status: WorkflowStatus;
  owner: string;
}

export interface AuditEntry {
  id: string;
  at: string;
  actor: 'agent' | 'operator' | 'system';
  action: string;
  status: 'succeeded' | 'failed' | 'pending';
  detail: string;
  correlationId?: string;
}

export interface PlatformState {
  incidents: Incident[];
  selectedIncidentId: string;
  workflow: Workflow;
  agentStatus: 'monitoring' | 'analyzing' | 'awaiting_approval' | 'complete';
  audit: AuditEntry[];
}

export type PlatformAction =
  | { type: 'select_incident'; incidentId: string }
  | { type: 'analyze_incident' }
  | { type: 'move_incident_triage' }
  | { type: 'submit_mitigation' }
  | { type: 'approve_escalation'; correlationId?: string }
  | { type: 'reject_escalation'; correlationId?: string }
  | { type: 'reset_platform' };

export interface PlatformSummary {
  selectedIncidentId: string;
  risk: number;
  workflowStatus: WorkflowStatus;
  agentStatus: PlatformState['agentStatus'];
  auditCount: number;
}
