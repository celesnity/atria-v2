import { parseEnvelope, parseUiIntent, UI_INTENT } from '../src/events';

const envelope = {
  event_id: 'e1',
  type: UI_INTENT,
  module: 'catalog',
  ts: '2026-07-15T00:00:00Z',
  source: 'agent',
  session_id: 's1',
  payload: { intent: { intent: 'navigate', route: 'home' } },
};

it('parseEnvelope accepts a well-formed envelope', () => {
  const env = parseEnvelope(envelope);
  expect(env?.event_id).toBe('e1');
  expect(env?.type).toBe(UI_INTENT);
});

it('parseEnvelope rejects a missing required field', () => {
  const { event_id, ...bad } = envelope;
  expect(parseEnvelope(bad)).toBeNull();
});

it('parseUiIntent accepts each intent variant', () => {
  expect(parseUiIntent({ intent: 'fill', form: 'f', values: { a: 1 } })?.intent).toBe('fill');
  expect(parseUiIntent({ intent: 'act', name: 'save' })?.intent).toBe('act');
});

it('parseUiIntent rejects an unknown intent kind', () => {
  expect(parseUiIntent({ intent: 'explode', form: 'f' })).toBeNull();
});
