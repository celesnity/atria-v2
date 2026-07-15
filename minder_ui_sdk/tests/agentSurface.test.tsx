import { render, screen, act } from '@testing-library/react';
import { AgentDriverProvider, type UiIntent } from '../src/agentDriver';
import { AgentRegistryProvider, Agent } from '../src/agentSurface/AgentSurface';
import { UI_INTENT } from '../src/events';
import { __resetSharedStreams } from '../src/stream';

let __seq = 0;

class FakeES {
  static last: FakeES | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeES.last = this;
  }
  emit(intent: UiIntent) {
    const env = {
      event_id: `e${(__seq += 1)}`,
      type: UI_INTENT,
      module: 'm',
      ts: '',
      source: 'agent',
      session_id: 's1',
      payload: { intent },
    };
    this.onmessage?.({ data: JSON.stringify(env) } as MessageEvent);
  }
  close() {}
}

afterEach(() => __resetSharedStreams());

function Demo({ onAdd }: { onAdd: () => void }) {
  return (
    <AgentDriverProvider apiBase="http://m" sessionId="s1">
      <AgentRegistryProvider sessionId="s1">
        <Agent.Page name="products" description="Kho">
          <Agent.Data name="list" description="rows" value={[{ id: 1 }]}>
            <div>table</div>
          </Agent.Data>
          <Agent.Button name="add" description="add product" onAct={onAdd}>
            <button>Add</button>
          </Agent.Button>
        </Agent.Page>
      </AgentRegistryProvider>
    </AgentDriverProvider>
  );
}

beforeEach(() => {
  (globalThis as any).EventSource = FakeES as unknown as typeof EventSource;
  (globalThis as any).fetch = vi.fn(() => Promise.resolve({ ok: true }));
});

it('renders children transparently and tags the button control', () => {
  render(<Demo onAdd={() => {}} />);
  expect(screen.getByText('table')).toBeTruthy();
  const btn = screen.getByText('Add');
  expect(btn.closest('[data-agent-control="products.add"]')).toBeTruthy();
});

it('an act intent runs the scoped action', () => {
  const onAdd = vi.fn();
  render(<Demo onAdd={onAdd} />);
  act(() => FakeES.last!.emit({ intent: 'act', name: 'products.add' }));
  expect(onAdd).toHaveBeenCalledOnce();
});

it('act on an unknown name does not throw and does not call onAct', () => {
  const onAdd = vi.fn();
  render(<Demo onAdd={onAdd} />);
  act(() => FakeES.last!.emit({ intent: 'act', name: 'products.nope' }));
  expect(onAdd).not.toHaveBeenCalled();
});
