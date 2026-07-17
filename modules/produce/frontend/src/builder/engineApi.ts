import { api } from '../api';

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export type NodeType = 'begin' | 'end' | 'human' | 'decision';

export interface GraphNode {
  uid: string;
  node_type: NodeType;
  key: string;
  label?: string;
  position: { x: number; y: number };
  config: Record<string, unknown>;
}

export interface GraphEdge {
  from: string; // node key (source)
  to: string;   // node key (target)
  branch: string;
}

export interface WorkflowGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface NodePortMeta {
  name: string;
  display_name: string;
  type: string;
  required: boolean;
  description: string;
  options: string[];
}

export interface NodeTypeMeta {
  node_type: string;
  display_name: string;
  description: string;
  category: string;
  inputs: NodePortMeta[];
}

export interface TemplateMeta {
  id: number;
  key: string;
  name: string;
  base_kind: string;
  config: Record<string, unknown>;
  color?: string;
  icon?: string;
}

export interface WorkflowSummary {
  id: number;
  key: string;
  name: string;
  scope_path: string;
  current_version_id: number | null;
}

export interface VersionSummary {
  id: number;
  version: number;
  status: string;
  note: string | null;
  published_at: string | null;
}

// ---------------------------------------------------------------------------
// API wrappers — all take engineBase as the first argument
// ---------------------------------------------------------------------------

export const getNodeTypes = (base: string, scopePath: string) =>
  api<{ primitives: NodeTypeMeta[]; templates: TemplateMeta[] }>(
    base,
    `/node-types?scope_path=${encodeURIComponent(scopePath)}`,
  );

export const listWorkflows = (base: string, scopePath: string) =>
  api<WorkflowSummary[]>(base, `/workflows?scope_path=${encodeURIComponent(scopePath)}`);

export const createWorkflow = (
  base: string,
  body: { key: string; name: string; scope_path: string; graph?: WorkflowGraph },
) => api<{ id: number }>(base, '/workflows', { method: 'POST', body: JSON.stringify(body) });

export const renameWorkflow = (base: string, id: number, name: string) =>
  api<WorkflowSummary>(base, `/workflows/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });

export const duplicateWorkflow = (base: string, id: number) =>
  api<{ id: number }>(base, `/workflows/${id}/duplicate`, { method: 'POST' });

export const putDraft = (base: string, id: number, graph: WorkflowGraph) =>
  api<{ id: number }>(base, `/workflows/${id}/draft`, {
    method: 'PUT',
    body: JSON.stringify({ graph }),
  });

export const validateWorkflow = (base: string, id: number) =>
  api<{ issues: string[] }>(base, `/workflows/${id}/validate`, { method: 'POST' });

export const publishWorkflow = (base: string, id: number, note: string) =>
  api<{ id: number; version: number; status: string }>(base, `/workflows/${id}/publish`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  });

export const listVersions = (base: string, id: number) =>
  api<VersionSummary[]>(base, `/workflows/${id}/versions`);

export const revertVersion = (base: string, id: number, version: number) =>
  api<{ id: number }>(base, `/workflows/${id}/versions/${version}/revert`, { method: 'POST' });

export const createTemplate = (
  base: string,
  body: { key: string; name: string; base_kind: string; config: Record<string, unknown>; scope_path?: string; color?: string; icon?: string },
) => api<TemplateMeta>(base, '/node-templates', { method: 'POST', body: JSON.stringify(body) });

export const updateTemplate = (
  base: string,
  id: number,
  body: Partial<{ name: string; config: Record<string, unknown>; color: string; icon: string }>,
) =>
  api<TemplateMeta>(base, `/node-templates/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

export const deleteTemplate = (base: string, id: number) =>
  api<void>(base, `/node-templates/${id}`, { method: 'DELETE' });
