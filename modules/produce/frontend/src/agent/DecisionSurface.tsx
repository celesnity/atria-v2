import {
  DecisionPacket,
  useDecision,
  useModuleEvents,
  type DecisionPacketData,
  type EventEnvelope,
} from 'minder-ui-sdk';

// G03: renders decision packets pushed by Minder for supervisor approval.
// The real SDK `useModuleEvents(apiBase, opts)` returns `{ events }` (an
// EventEnvelope[] ring buffer over /connector/stream) — there is no `packets`
// field — so we derive decision packets from the event payloads. `DecisionPacket`
// takes `{ packet, onDecision, pending }`; posting the verdict back is done via
// `useDecision(apiBase).submit`, not an `apiBase` prop.
function isDecision(payload: unknown): payload is DecisionPacketData {
  return (
    !!payload &&
    typeof payload === 'object' &&
    ((payload as { kind?: string }).kind === 'decision' ||
      (payload as { card_type?: string }).card_type === 'decision_packet') &&
    typeof (payload as { action?: unknown }).action === 'string'
  );
}

export default function DecisionSurface({ apiBase }: { apiBase: string }) {
  const { events } = useModuleEvents(apiBase);
  const { submit, pending } = useDecision(apiBase);
  const packets = events
    .filter((e: EventEnvelope) => isDecision(e.payload))
    .map((e: EventEnvelope) => e.payload as DecisionPacketData);
  if (!packets.length) return null;
  return (
    <div style={{ marginBottom: 16 }}>
      {packets.map((p, i) => (
        <DecisionPacket key={i} packet={p} onDecision={(d) => { void submit(d); }} pending={pending} />
      ))}
    </div>
  );
}
