import { render, screen, fireEvent, act } from '@testing-library/react';
import { useState } from 'react';
import { AgentRegistryProvider, Agent } from '../src/agentSurface/AgentSurface';

let __ver = 0;
beforeEach(() => {
  vi.useFakeTimers();
  __ver = 0;
  (globalThis as any).fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ version: (__ver += 1) }),
    }),
  );
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function fetchCalls() {
  return (globalThis as any).fetch.mock.calls as any[];
}

it('first push is a full snapshot with scoped names to /connector/ui/snapshot', async () => {
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
  await act(async () => {
    await vi.advanceTimersByTimeAsync(200);
  });
  const calls = fetchCalls();
  expect(calls.length).toBeGreaterThan(0);
  const [url, opts] = calls[calls.length - 1];
  expect(url).toBe('http://m/connector/ui/snapshot');
  const body = JSON.parse(opts.body);
  expect(body.kind).toBe('snapshot');
  expect(body.session_id).toBe('s1');
  expect(body.snapshot.page).toBe('products');
  expect(body.snapshot.data.map((d: any) => d.name)).toContain('products.list');
  expect(body.snapshot.actions.map((a: any) => a.name)).toContain('products.add');
});

it('sends a delta after the first full snapshot', async () => {
  function Stateful() {
    const [n, setN] = useState(1);
    return (
      <AgentRegistryProvider apiBase="http://m/" sessionId="s1">
        <Agent.Page name="products">
          <Agent.Data name="count" value={n}>
            <button onClick={() => setN(2)}>inc</button>
          </Agent.Data>
        </Agent.Page>
      </AgentRegistryProvider>
    );
  }
  render(<Stateful />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(200); // full snapshot -> version 1
  });
  fireEvent.click(screen.getByText('inc'));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(200); // delta
  });

  const last = JSON.parse(fetchCalls().at(-1)![1].body);
  expect(last.kind).toBe('delta');
  expect(last.base_version).toBe(1);
  expect(Array.isArray(last.delta)).toBe(true);
  expect(last.delta.length).toBeGreaterThan(0);
});
