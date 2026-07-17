import { describe, it, expect } from 'vitest';
import { toFlow, fromFlow } from './graphMap';
import type { WorkflowGraph } from './engineApi';

const G: WorkflowGraph = {
  nodes: [
    { uid: 'a', node_type: 'begin', key: 'start', position: { x: 0, y: 0 }, config: {} },
    { uid: 'b', node_type: 'human', key: 'm', position: { x: 200, y: 0 }, config: { instructions: 'do' } },
    { uid: 'd', node_type: 'decision', key: 'chk', position: { x: 400, y: 0 }, config: { condition: { left: 1, operator: '<=', right: 10 } } },
    { uid: 'z', node_type: 'end', key: 'done', position: { x: 600, y: 0 }, config: {} },
  ],
  edges: [
    { from: 'start', to: 'm', branch: 'default' },
    { from: 'm', to: 'chk', branch: 'default' },
    { from: 'chk', to: 'done', branch: 'pass' },
    { from: 'chk', to: 'done', branch: 'else' },
  ],
};

describe('graphMap', () => {
  it('round-trips graph -> flow -> graph', () => {
    const { nodes, edges } = toFlow(G);
    const back = fromFlow(nodes, edges);
    expect(back).toEqual(G);
  });

  it('maps edges by uid with branch on sourceHandle', () => {
    const { edges } = toFlow(G);
    const passEdge = edges.find((e) => e.data?.branch === 'pass')!;
    expect(passEdge.source).toBe('d');   // chk uid
    expect(passEdge.target).toBe('z');   // done uid
    expect(passEdge.sourceHandle).toBe('pass');
  });
});
