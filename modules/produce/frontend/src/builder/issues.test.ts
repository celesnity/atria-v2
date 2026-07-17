import { describe, it, expect } from 'vitest';
import { mapIssues } from './issues';

const graph = { nodes: [{ uid: 'd', node_type: 'decision', key: 'chk', position: { x: 0, y: 0 }, config: {} }], edges: [] } as any;

it('attaches quoted-key issues to the node', () => {
  const r = mapIssues(["decision 'chk' must have a 'pass' branch", 'no end reachable from begin'], graph);
  expect(r.byNodeKey['chk']).toHaveLength(1);
  expect(r.general).toEqual(['no end reachable from begin']);
});

describe('mapIssues additional cases', () => {
  it('puts issues with no matching key into general', () => {
    const r = mapIssues(['workflow must have at least one begin node'], graph);
    expect(r.byNodeKey).toEqual({});
    expect(r.general).toHaveLength(1);
  });

  it('handles empty issues array', () => {
    const r = mapIssues([], graph);
    expect(r.byNodeKey).toEqual({});
    expect(r.general).toEqual([]);
  });

  it('skips quoted tokens that are not known keys', () => {
    const r = mapIssues(["decision 'chk' must have a 'pass' branch"], graph);
    // 'pass' is not a node key, so it should not appear in byNodeKey; 'chk' is
    expect(Object.keys(r.byNodeKey)).toEqual(['chk']);
  });
});
