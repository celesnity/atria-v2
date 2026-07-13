import { render, act } from '@testing-library/react';
import { AgentRegistryProvider, Agent } from '../src/agentSurface/AgentSurface';

beforeEach(() => {
  vi.useFakeTimers();
  (globalThis as any).fetch = vi.fn(() => Promise.resolve({ ok: true }));
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it('POSTs a debounced snapshot with scoped names to /connector/ui/snapshot', () => {
  render(
    <AgentRegistryProvider apiBase="http://m/" sessionId="s1">
      <Agent.Page name="products" description="Kho">
        <Agent.Data name="list" description="rows" value={[{ id: 1 }]}>
          <div>t</div>
        </Agent.Data>
        <Agent.Button name="add" description="add" onAct={() => {}}>
          <button>Add</button>
        </Agent.Button>
      </Agent.Page>
    </AgentRegistryProvider>,
  );
  act(() => {
    vi.advanceTimersByTime(200);
  });
  const fetchMock = (globalThis as any).fetch as ReturnType<typeof vi.fn>;
  const calls = fetchMock.mock.calls;
  expect(calls.length).toBeGreaterThan(0);
  const [url, opts] = calls[calls.length - 1];
  expect(url).toBe('http://m/connector/ui/snapshot');
  const body = JSON.parse(opts.body);
  expect(body.session_id).toBe('s1');
  expect(body.snapshot.page).toBe('products');
  expect(body.snapshot.data.map((d: any) => d.name)).toContain('products.list');
  expect(body.snapshot.actions.map((a: any) => a.name)).toContain('products.add');
});
