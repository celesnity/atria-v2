import { render, screen, fireEvent, act } from '@testing-library/react';
import { AgentDriverProvider } from '../src/agentDriver';
import { AgentPresence, attributionLabel } from '../src/presence';
import { MinderThemeProvider } from '../src/theme';
import type { EventEnvelope } from '../src/agentContext';
import type { UiIntent } from '../src/agentDriver';

/** One fake EventSource per URL, so a test can push into the right stream:
 * the driver's `/connector/ui/intents` and presence's `/connector/events`. */
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
  close() {}
}

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
    events: FakeES.byUrl.get('http://m/connector/events')!,
    intents: FakeES.byUrl.get('http://m/connector/ui/intents?session=s1')!,
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
  act(() => intents.push(intent));
  expect(document.querySelector('[data-minder-presence="proposing"]')).toBeTruthy();
  expect(screen.getByText('Create ABC?')).toBeTruthy();
  expect(document.querySelector('[data-minder-ghost-cursor="proposing"]')).toBeTruthy();
});

it('follows the agent to the field it is filling/focusing', () => {
  const { intents } = setup();
  act(() => intents.push({ intent: 'fill', form: 'add_product', values: { sku: 'T-1' } } as UiIntent));
  expect(document.querySelector('[data-minder-presence="acting"]')).toBeTruthy();
  expect(screen.getByText('Minder filled the form')).toBeTruthy();
  expect(document.querySelector('[data-minder-ghost-cursor="acting"]')).toBeTruthy();

  act(() => intents.push({ intent: 'focus', form: 'add_product', field: 'category' } as UiIntent));
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
