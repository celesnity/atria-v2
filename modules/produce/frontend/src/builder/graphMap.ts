/**
 * Pure: convert between WorkflowGraph (engine representation) and React Flow nodes/edges.
 *
 * Key design decisions:
 * - Engine graph edges reference nodes by **key** (human-readable id).
 * - React Flow nodes use **uid** as the node id.
 * - toFlow builds key→uid and uid→key maps; fromFlow inverts them.
 * - sourceHandle = branch so decision multi-handle connections work correctly.
 */

import type { Node as RFNode, Edge as RFEdge } from '@xyflow/react';
import type { WorkflowGraph, GraphNode, GraphEdge } from './engineApi';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FlowNodeData extends Record<string, unknown> {
  node_type: GraphNode['node_type'];
  key: string;
  label?: string;
  config: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// toFlow — WorkflowGraph → React Flow nodes + edges
// ---------------------------------------------------------------------------

export function toFlow(graph: WorkflowGraph): { nodes: RFNode<FlowNodeData>[]; edges: RFEdge[] } {
  // Build key → uid lookup
  const uidByKey: Record<string, string> = {};
  for (const n of graph.nodes) {
    uidByKey[n.key] = n.uid;
  }

  const nodes: RFNode<FlowNodeData>[] = graph.nodes.map((n) => ({
    id: n.uid,
    type: 'flowNode',
    position: { x: n.position.x, y: n.position.y },
    data: {
      node_type: n.node_type,
      key: n.key,
      label: n.label,
      config: n.config,
    },
  }));

  const edges: RFEdge[] = graph.edges.map((e, idx) => {
    const sourceUid = uidByKey[e.from];
    const targetUid = uidByKey[e.to];
    return {
      id: `e-${idx}-${e.from}-${e.to}-${e.branch}`,
      source: sourceUid,
      target: targetUid,
      sourceHandle: e.branch,
      label: e.branch,
      data: { branch: e.branch },
    };
  });

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// fromFlow — React Flow nodes + edges → WorkflowGraph
// ---------------------------------------------------------------------------

export function fromFlow(nodes: RFNode<FlowNodeData>[], edges: RFEdge[]): WorkflowGraph {
  // Build uid → key lookup from current node data
  const keyByUid: Record<string, string> = {};
  for (const n of nodes) {
    keyByUid[n.id] = n.data.key;
  }

  const graphNodes: GraphNode[] = nodes.map((n) => ({
    uid: n.id,
    node_type: n.data.node_type,
    key: n.data.key,
    label: n.data.label,
    position: { x: n.position.x, y: n.position.y },
    config: n.data.config,
  }));

  const graphEdges: GraphEdge[] = edges.map((e) => ({
    from: keyByUid[e.source],
    to: keyByUid[e.target],
    branch: (e.data as { branch: string } | undefined)?.branch ?? String(e.sourceHandle ?? 'default'),
  }));

  return { nodes: graphNodes, edges: graphEdges };
}
