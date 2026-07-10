import type { Message } from '../types';
import { mapMaintenanceAnswer } from './maintenanceAnswer';
import { mapModuleCard } from './moduleCard';

/**
 * Card render registry — keyed by the WS `card_type` a service module broadcasts.
 *
 * The backend (atria/core/modules/remote.py) sends every module's UI card as a WS
 * message whose `type` is a per-module `card_type` string: either one the module
 * chose (e.g. `maintenance_answer`) or the default `"{module}_card"`. This registry
 * maps that payload to a chat Message; MessageList then routes the Message.role to
 * a component. Known card_types get a bespoke mapper; everything else falls back to
 * the generic module card (mapped in the WS handler via mapModuleCard).
 *
 * Add a new bespoke card by registering its mapper here and a `role` branch in
 * MessageList — no switch to grow, and unknown types keep working via the fallback.
 */
export type CardMapper = (data: any) => Message;

export const CARD_MAPPERS: Record<string, CardMapper> = {
  maintenance_answer: mapMaintenanceAnswer,
};

/** True for any WS message type this registry can render as a chat card. */
export function isCardType(type: string): boolean {
  return type in CARD_MAPPERS || type.endsWith('_card');
}

/** Map a card WS payload to a Message: bespoke mapper if known, else generic. */
export function mapCard(cardType: string, data: any): Message {
  const mapper = CARD_MAPPERS[cardType];
  return mapper ? mapper(data) : mapModuleCard(cardType, data);
}
