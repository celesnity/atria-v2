import { describe, it, expect, vi } from 'vitest';
import { createRegistry, MAX_VALUE_CHARS } from '../src/agentSurface/registry';

describe('registry', () => {
  it('snapshots page, data and actions', () => {
    const r = createRegistry();
    r.setPage('products');
    r.setData({ name: 'products.list', description: 'rows', value: [{ id: 1 }] });
    r.setAction({ name: 'products.add', description: 'add', onAct: () => {} });
    const s = r.snapshot();
    expect(s.page).toBe('products');
    expect(s.data).toEqual([{ name: 'products.list', description: 'rows', value: [{ id: 1 }] }]);
    expect(s.actions).toEqual([{ name: 'products.add', description: 'add' }]);
  });

  it('run() invokes the matching action and returns true; unknown returns false', () => {
    const r = createRegistry();
    const spy = vi.fn();
    r.setAction({ name: 'a', onAct: spy });
    expect(r.run('a')).toBe(true);
    expect(spy).toHaveBeenCalledOnce();
    expect(r.run('missing')).toBe(false);
  });

  it('removeData / removeAction drop entries from the snapshot', () => {
    const r = createRegistry();
    r.setData({ name: 'd', value: 1 });
    r.removeData('d');
    expect(r.snapshot().data).toEqual([]);
  });

  it('caps oversized values and flags truncated', () => {
    const r = createRegistry();
    const big = 'x'.repeat(MAX_VALUE_CHARS + 10);
    r.setData({ name: 'd', value: big });
    const entry = r.snapshot().data[0];
    expect(entry.truncated).toBe(true);
    expect((entry.value as string).length).toBe(MAX_VALUE_CHARS);
  });

  it('subscribe fires on mutation and unsubscribe stops it', () => {
    const r = createRegistry();
    const fn = vi.fn();
    const off = r.subscribe(fn);
    r.setPage('p');
    expect(fn).toHaveBeenCalledOnce();
    off();
    r.setPage('q');
    expect(fn).toHaveBeenCalledOnce();
  });
});
