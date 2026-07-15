import { z } from 'zod';

/** The single event type carrying an agent→UI intent. */
export const UI_INTENT = 'ui.intent';

/** The agent-drives-the-real-UI command union. Payload of a `ui.intent` event. */
export const UiIntentSchema = z.discriminatedUnion('intent', [
  z.object({ intent: z.literal('navigate'), route: z.string() }),
  z.object({
    intent: z.literal('fill'),
    form: z.string(),
    values: z.record(z.unknown()),
    partial: z.boolean().optional(),
  }),
  z.object({
    intent: z.literal('focus'),
    form: z.string().nullable().optional(),
    field: z.string(),
  }),
  z.object({ intent: z.literal('highlight'), control: z.string() }),
  z.object({
    intent: z.literal('request_confirm'),
    target: z.string(),
    summary: z.string().nullable().optional(),
  }),
  z.object({ intent: z.literal('submit'), form: z.string() }),
  z.object({ intent: z.literal('act'), name: z.string() }),
]);
export type UiIntent = z.infer<typeof UiIntentSchema>;

/** Who acted — distinguishes an agent acting for a user from a human. */
export const EventActorSchema = z.object({
  kind: z.enum(['agent', 'human', 'system']),
  agent_id: z.string().nullable().optional(),
  on_behalf_of: z.string().nullable().optional(),
});
export type EventActor = z.infer<typeof EventActorSchema>;

/** A normalized, timestamped, sourced record of something that happened. */
export const EventEnvelopeSchema = z.object({
  event_id: z.string(),
  type: z.string(),
  module: z.string(),
  ts: z.string(),
  source: z.string(),
  actor: EventActorSchema.nullable().optional(),
  session_id: z.string().nullable().optional(),
  payload: z.unknown(),
});
export type EventEnvelope<P = unknown> = Omit<
  z.infer<typeof EventEnvelopeSchema>,
  'payload'
> & { payload: P };

/** Validate an inbound envelope; return null (caller warns + drops) on failure. */
export function parseEnvelope(data: unknown): EventEnvelope | null {
  const r = EventEnvelopeSchema.safeParse(data);
  return r.success ? (r.data as EventEnvelope) : null;
}

/** Validate a `ui.intent` payload's `intent` object. */
export function parseUiIntent(data: unknown): UiIntent | null {
  const r = UiIntentSchema.safeParse(data);
  return r.success ? r.data : null;
}
