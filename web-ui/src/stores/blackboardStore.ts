import { create } from 'zustand';
import { wsClient } from '../api/websocket';

export interface BidView {
  responder: string;
  volunteered: boolean;
  reason: string;
  confidence: number;
}
export interface ResponseView {
  responder: string;
  content: string;
  confidence: number;
}
export interface RequestView {
  requestId: string;
  prompt: string;
  bids: BidView[];
  responses: ResponseView[];
  status: 'open' | 'answered';
  startedAt: number;
}

interface BlackboardState {
  requests: Record<string, RequestView>;
  order: string[];
  clear(): void;
}

export const useBlackboardStore = create<BlackboardState>((set) => ({
  requests: {},
  order: [],
  clear: () => set({ requests: {}, order: [] }),
}));

function upsert(id: string, mut: (r: RequestView) => RequestView) {
  useBlackboardStore.setState((s) => {
    const existing = s.requests[id];
    const base: RequestView = existing ?? {
      requestId: id, prompt: '', bids: [], responses: [], status: 'open', startedAt: Date.now(),
    };
    return {
      requests: { ...s.requests, [id]: mut(base) },
      order: existing ? s.order : [id, ...s.order],
    };
  });
}

// Exported for unit tests; also wired to wsClient below.
export function __handleBoardEvent(type: string, data: any) {
  if (type === 'blackboard.request') {
    upsert(data.id, (r) => ({ ...r, prompt: data.prompt ?? r.prompt }));
  } else if (type === 'blackboard.bid') {
    upsert(data.request_id, (r) => ({
      ...r,
      bids: [...r.bids.filter((b) => b.responder !== data.responder), {
        responder: data.responder, volunteered: !!data.volunteered,
        reason: data.reason ?? '', confidence: Number(data.confidence ?? 0),
      }],
    }));
  } else if (type === 'blackboard.response') {
    upsert(data.request_id, (r) => ({
      ...r,
      status: 'answered',
      responses: [...r.responses.filter((x) => x.responder !== data.responder), {
        responder: data.responder, content: data.content ?? '',
        confidence: Number(data.confidence ?? 0),
      }],
    }));
  }
}

export function initBlackboardStore() {
  wsClient.on('blackboard.request', (m) => __handleBoardEvent('blackboard.request', m.data));
  wsClient.on('blackboard.bid', (m) => __handleBoardEvent('blackboard.bid', m.data));
  wsClient.on('blackboard.response', (m) => __handleBoardEvent('blackboard.response', m.data));
}

initBlackboardStore();
