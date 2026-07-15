import { render, screen, fireEvent, act } from '@testing-library/react';
import { AgentDriverProvider } from '../src/agentDriver';
import { AgentPresence, attributionLabel } from '../src/presence';
import { MinderThemeProvider } from '../src/theme';
import { UI_INTENT } from '../src/events';
import { __resetSharedStreams } from '../src/stream';
import type { EventEnvelope } from '../src/agentContext';
import type { UiIntent } from '../src/agentDriver';

let __seq = 0;

/** One fake EventSource per URL. Both the driver and presence now subscribe to
 * the merged `/connector/stream` — presence's domain-event reader uses the
 * session-less URL, the driver uses `?session=s1`. `push` sends a raw envelope;
 * `pushIntent` wraps a UiIntent as a `ui.intent` envelope. */
class FakeES {
  static byUrl = new Map<string, FakeES>();
  onmessage: ((e: MessageEvent) => void) | null = null;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeES.byUrl.set(url, this);
  }
  push(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) } as MessageEvent);
  }
  pushIntent(intent: UiIntent) {
    this.push({
      event_id: `e${(__seq += 1)}`,
      type: UI_INTENT,
      module: 'm',
      ts: '',
      source: 'agent',
      session_id: 's1',
      payload: { intent },
    });
  }
  close() {}
}

afterEach(() => __resetSharedStreams());

function setup() {
  FakeES.byUrl.clear();
  vi.stubGlobal('EventSource', FakeES as unknown as typeof EventSource);
  render(
    <MinderThemeProvider theme="dark">
      <AgentDriverProvider apiBase="http://m" sessionId="s1">
        <button data-minder-approve="">Approve</button>
        <AgentPresence apiBase="http://m" />
      </AgentDriverProvider>
    </MinderThemeProvider>,
  );
  return {
    events: FakeES.byUrl.get('http://m/connector/stream')!,
    intents: FakeES.byUrl.get('http://m/connector/stream?session=s1')!,
  };
}

const completed = (tool: string, kind: 'agent' | 'human'): EventEnvelope => ({
  event_id: '1',
  type: 'action.completed',
  module: 'm',
  ts: '',
  source: kind,
  actor: { kind, on_behalf_of: kind === 'human' ? 'bob' : null },
  payload: { tool, risk: 'low' },
});

it('is idle (renders nothing) until the agent acts', () => {
  setup();
  expect(document.querySelector('[data-minder-presence]')).toBeNull();
});

it('animates a committed low-risk action as done, attributed to Minder', () => {
  const { events } = setup();
  act(() => events.push(completed('create_product', 'agent')));
  expect(document.querySelector('[data-minder-presence="acting"]')).toBeTruthy();
  expect(screen.getByText(/did: create_product/)).toBeTruthy();
  expect(screen.getByText('Minder')).toBeTruthy(); // attribution badge
  expect(document.querySelector('[data-minder-ghost-cursor="acting"]')).toBeTruthy();
});

it('renders a high-risk proposal as a parked cursor awaiting approval', () => {
  const { intents } = setup();
  const intent: UiIntent = { intent: 'request_confirm', target: 'add_product', summary: 'Create ABC?' };
  act(() => intents.pushIntent(intent));
  expect(document.querySelector('[data-minder-presence="proposing"]')).toBeTruthy();
  expect(screen.getByText('Create ABC?')).toBeTruthy();
  expect(document.querySelector('[data-minder-ghost-cursor="proposing"]')).toBeTruthy();
});

it('follows the agent to the field it is filling/focusing', () => {
  const { intents } = setup();
  act(() => intents.pushIntent({ intent: 'fill', form: 'add_product', values: { sku: 'T-1' } }));
  expect(document.querySelector('[data-minder-presence="acting"]')).toBeTruthy();
  expect(screen.getByText('Minder filled the form')).toBeTruthy();
  expect(document.querySelector('[data-minder-ghost-cursor="acting"]')).toBeTruthy();

  act(() => intents.pushIntent({ intent: 'focus', form: 'add_product', field: 'category' }));
  expect(screen.getByText('Fill this next')).toBeTruthy();
});

it('lets the operator dismiss the presence (interrupt)', () => {
  const { events } = setup();
  act(() => events.push(completed('ship_order', 'agent')));
  expect(document.querySelector('[data-minder-presence]')).toBeTruthy();
  fireEvent.click(screen.getByLabelText('Dismiss Minder'));
  expect(document.querySelector('[data-minder-presence]')).toBeNull();
});

it('distinguishes agent vs human attribution', () => {
  expect(attributionLabel({ kind: 'agent' })).toBe('Minder');
  expect(attributionLabel({ kind: 'human', on_behalf_of: 'bob' })).toBe('bob');
  expect(attributionLabel({ kind: 'human' })).toBe('You');
  expect(attributionLabel(null)).toBe('System');
});
