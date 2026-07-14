import { getSharedStream, __resetSharedStreams } from '../src/stream';
import { UI_INTENT } from '../src/events';

class FakeES {
  static instances: FakeES[] = [];
  onmessage: ((e: MessageEvent) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeES.instances.push(this);
  }
  emit(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) } as MessageEvent);
  }
  close() {
    this.closed = true;
  }
}

const env = (id: string) => ({
  event_id: id,
  type: UI_INTENT,
  module: 'm',
  ts: 't',
  source: 'agent',
  payload: {},
});

beforeEach(() => {
  FakeES.instances = [];
  __resetSharedStreams();
  vi.stubGlobal('EventSource', FakeES as unknown as typeof EventSource);
});
afterEach(() => {
  __resetSharedStreams();
  vi.restoreAllMocks();
});

it('two subscribers to the same URL share one EventSource', () => {
  const a: string[] = [];
  const b: string[] = [];
  getSharedStream('http://m/s', (e) => a.push(e.event_id));
  getSharedStream('http://m/s', (e) => b.push(e.event_id));
  expect(FakeES.instances.length).toBe(1);
  FakeES.instances[0].emit(env('e1'));
  expect(a).toEqual(['e1']);
  expect(b).toEqual(['e1']);
});

it('closes the underlying EventSource only after the last unsubscribe', () => {
  const h1 = getSharedStream('http://m/s', () => {});
  const h2 = getSharedStream('http://m/s', () => {});
  h1.close();
  expect(FakeES.instances[0].closed).toBe(false);
  h2.close();
  expect(FakeES.instances[0].closed).toBe(true);
});

it('drops an invalid envelope without throwing', () => {
  const seen: string[] = [];
  getSharedStream('http://m/s', (e) => seen.push(e.event_id));
  FakeES.instances[0].emit({ nope: true });
  expect(seen).toEqual([]);
});
