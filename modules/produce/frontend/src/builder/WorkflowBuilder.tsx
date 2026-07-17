/**
 * WorkflowBuilder — xyflow canvas with autosave, palette, inspector and version bar.
 */
import '@xyflow/react/dist/style.css';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  type NodeChange,
  type EdgeChange,
  type OnNodesChange,
  type OnEdgesChange,
  BackgroundVariant,
  type ReactFlowInstance,
  applyNodeChanges,
  applyEdgeChanges,
} from '@xyflow/react';
import { Box, Group, Text, ActionIcon } from '@mantine/core';
import { IconArrowLeft, IconCheck } from '@tabler/icons-react';
import FlowNode, { type FlowNodeData } from './nodes/FlowNode';
import Palette from './Palette';
import Inspector from './Inspector';
import VersionBar from './VersionBar';
import { toFlow, fromFlow } from './graphMap';
import { putDraft } from './engineApi';
import type { WorkflowSummary, WorkflowGraph, NodeType, NodeTypeMeta } from './engineApi';
import { useApiQuery } from '../hooks/useApiQuery';
import { useToast } from '../ui/Toast';

// ---------------------------------------------------------------------------
// nodeTypes must be stable (defined outside the component)
// ---------------------------------------------------------------------------

const nodeTypes = { flowNode: FlowNode };

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type FlowNode_ = Node<FlowNodeData>;
type FlowEdge_ = Edge;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface WorkflowBuilderProps {
  engineBase: string;
  workflow: WorkflowSummary;
  onBack: () => void;
  scopePath?: string;
}

// ---------------------------------------------------------------------------
// WorkflowBuilder
// ---------------------------------------------------------------------------

export default function WorkflowBuilder({
  engineBase,
  workflow,
  onBack,
  scopePath = 'site',
}: WorkflowBuilderProps) {
  const { notify } = useToast();

  // ------------------------------------------------------------------
  // Load draft graph from the server
  // ------------------------------------------------------------------
  const { data: draftGraph, refetch: refetchDraft } = useApiQuery<WorkflowGraph>(
    engineBase,
    `/workflows/${workflow.id}/draft`,
  );

  // ------------------------------------------------------------------
  // Node-type metadata (for inspector)
  // ------------------------------------------------------------------
  const nodeTypesQ = useApiQuery<{ primitives: NodeTypeMeta[]; templates: unknown[] }>(
    engineBase,
    `/node-types?scope_path=${encodeURIComponent(scopePath)}`,
  );
  const primitives = nodeTypesQ.data?.primitives ?? [];

  // ------------------------------------------------------------------
  // React Flow state — manage manually so we have typed arrays
  // ------------------------------------------------------------------
  const [nodes, setNodes] = useState<FlowNode_[]>([]);
  const [edges, setEdges] = useState<FlowEdge_[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const selectedNode = nodes.find((n: FlowNode_) => n.id === selectedNodeId);

  const onNodesChange: OnNodesChange<FlowNode_> = useCallback(
    (changes: NodeChange<FlowNode_>[]) => setNodes((nds: FlowNode_[]) => applyNodeChanges(changes, nds)),
    [],
  );
  const onEdgesChange: OnEdgesChange<FlowEdge_> = useCallback(
    (changes: EdgeChange<FlowEdge_>[]) => setEdges((eds: FlowEdge_[]) => applyEdgeChanges(changes, eds)),
    [],
  );

  // ------------------------------------------------------------------
  // Seeding — once the draft is loaded, seed nodes + edges
  // ------------------------------------------------------------------
  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current) return;
    if (!draftGraph) return;
    const { nodes: rfNodes, edges: rfEdges } = toFlow(draftGraph);
    setNodes(rfNodes as FlowNode_[]);
    setEdges(rfEdges);
    seeded.current = true;
  }, [draftGraph]);

  // ------------------------------------------------------------------
  // Autosave — debounced 600ms, guarded during initial load
  // ------------------------------------------------------------------
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [savedIndicator, setSavedIndicator] = useState(false);
  const nodesRef = useRef<FlowNode_[]>(nodes);
  const edgesRef = useRef<FlowEdge_[]>(edges);
  nodesRef.current = nodes;
  edgesRef.current = edges;

  const scheduleSave = useCallback(() => {
    if (!seeded.current) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      try {
        const graph = fromFlow(
          nodesRef.current as Parameters<typeof fromFlow>[0],
          edgesRef.current,
        );
        await putDraft(engineBase, workflow.id, graph);
        setSavedIndicator(true);
        setTimeout(() => setSavedIndicator(false), 2000);
      } catch (err) {
        notify(err instanceof Error ? err.message : 'Autosave failed', 'err');
      }
    }, 600);
  }, [engineBase, workflow.id, notify]);

  // Schedule save when nodes or edges change (after seed)
  useEffect(() => {
    if (!seeded.current) return;
    scheduleSave();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges]);

  // ------------------------------------------------------------------
  // React Flow instance (for viewport → flow position)
  // ------------------------------------------------------------------
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance<FlowNode_, FlowEdge_> | null>(null);

  // ------------------------------------------------------------------
  // Connect handler
  // ------------------------------------------------------------------
  const onConnect = useCallback(
    (connection: Connection) => {
      const branch = connection.sourceHandle ?? 'default';
      setEdges((eds: FlowEdge_[]) =>
        addEdge<FlowEdge_>(
          { id: '', ...connection, data: { branch } } as unknown as FlowEdge_,
          eds,
        ),
      );
    },
    [],
  );

  // ------------------------------------------------------------------
  // Palette → insert node
  // ------------------------------------------------------------------
  const onAdd = useCallback(
    (spec: { node_type: NodeType; templateConfig?: Record<string, unknown> }) => {
      const center = rfInstance
        ? rfInstance.screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 })
        : { x: 100 + Math.random() * 200, y: 100 + Math.random() * 200 };
      const uid = crypto.randomUUID();
      const newNode: FlowNode_ = {
        id: uid,
        type: 'flowNode',
        position: center,
        data: {
          node_type: spec.node_type,
          key: `${spec.node_type}_${uid.slice(0, 6)}`,
          label: '',
          config: spec.templateConfig ?? {},
          invalid: false,
        },
      };
      setNodes((nds: FlowNode_[]) => [...nds, newNode]);
    },
    [rfInstance],
  );

  // ------------------------------------------------------------------
  // Inspector onChange
  // ------------------------------------------------------------------
  const onInspectorChange = useCallback(
    (patch: { key?: string; label?: string; config?: Record<string, unknown> }) => {
      if (!selectedNodeId) return;
      setNodes((nds: FlowNode_[]) =>
        nds.map((n: FlowNode_) => {
          if (n.id !== selectedNodeId) return n;
          return {
            ...n,
            data: {
              ...n.data,
              ...(patch.key !== undefined ? { key: patch.key } : {}),
              ...(patch.label !== undefined ? { label: patch.label } : {}),
              ...(patch.config !== undefined ? { config: patch.config } : {}),
            },
          };
        }),
      );
    },
    [selectedNodeId],
  );

  // ------------------------------------------------------------------
  // Set invalid flag on nodes (from VersionBar)
  // ------------------------------------------------------------------
  const setNodeInvalid = useCallback(
    (invalidKeys: Set<string>) => {
      setNodes((nds: FlowNode_[]) =>
        nds.map((n: FlowNode_) => {
          const isInvalid = invalidKeys.has(n.data.key);
          if (n.data.invalid === isInvalid) return n;
          return { ...n, data: { ...n.data, invalid: isInvalid } };
        }),
      );
    },
    [],
  );

  // ------------------------------------------------------------------
  // Build graph for VersionBar
  // ------------------------------------------------------------------
  const getGraph = useCallback(
    () => fromFlow(nodes as Parameters<typeof fromFlow>[0], edges),
    [nodes, edges],
  );

  // ------------------------------------------------------------------
  // Node-type meta lookup for inspector
  // ------------------------------------------------------------------
  const nodeTypeMeta: NodeTypeMeta | null = selectedNode
    ? (primitives.find((p) => p.node_type === selectedNode.data.node_type) ?? null)
    : null;

  return (
    <Box style={{ height: 'calc(100vh - 200px)', display: 'flex', flexDirection: 'column' }}>
      {/* Top bar */}
      <Group
        justify="space-between"
        px="md"
        py="xs"
        style={{ borderBottom: '1px solid var(--mantine-color-default-border)', flexShrink: 0 }}
      >
        <Group gap="sm">
          <ActionIcon variant="subtle" aria-label="Back to workflow list" onClick={onBack}>
            <IconArrowLeft size={16} />
          </ActionIcon>
          <Text fw={600} size="sm">{workflow.name}</Text>
          {savedIndicator && (
            <Group gap={4} style={{ opacity: 0.6 }}>
              <IconCheck size={12} />
              <Text size="xs" c="dimmed">saved</Text>
            </Group>
          )}
        </Group>
        <VersionBar
          engineBase={engineBase}
          workflowId={workflow.id}
          getGraph={getGraph}
          nodes={nodes}
          setNodeInvalid={setNodeInvalid}
          onDraftReload={() => {
            seeded.current = false;
            refetchDraft();
          }}
        />
      </Group>

      {/* Canvas area */}
      <Box style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Palette */}
        <Box
          style={{
            width: 220,
            flexShrink: 0,
            borderRight: '1px solid var(--mantine-color-default-border)',
            overflowY: 'auto',
            padding: '8px 4px',
          }}
        >
          <Palette engineBase={engineBase} scopePath={scopePath} onAdd={onAdd} />
        </Box>

        {/* ReactFlow canvas */}
        <Box style={{ flex: 1 }}>
          <ReactFlow<FlowNode_, FlowEdge_>
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            onNodeClick={(_evt: React.MouseEvent, node: FlowNode_) => setSelectedNodeId(node.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            onInit={(instance: ReactFlowInstance<FlowNode_, FlowEdge_>) => setRfInstance(instance)}
            fitView
          >
            <Background variant={BackgroundVariant.Dots} />
            <Controls />
            <MiniMap zoomable pannable />
          </ReactFlow>
        </Box>
      </Box>

      {/* Inspector drawer (right) */}
      <Inspector
        engineBase={engineBase}
        node={selectedNode ?? null}
        nodeTypeMeta={nodeTypeMeta}
        scopePath={scopePath}
        onChange={onInspectorChange}
        onClose={() => setSelectedNodeId(null)}
      />
    </Box>
  );
}
