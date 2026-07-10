import type { Message } from '../types';
import { mapModuleCard } from './moduleCard';

/**
 * Card render registry — keyed by the WS `card_type` a service module broadcasts.
 *
 * The backend (atria/core/modules/remote.py) sends every module's UI card as a WS
 * message whose `type` is a per-module `card_type` string: either one the module
 * chose (e.g. `maintenance_answer`) or the default `"{module}_card"`. This registry
 * maps that payload to a chat Message; MessageList then routes the Message.role to
 * a component. All card_types fall back to the generic module card (mapModuleCard).
 * Federated blocks (render:"remote") are handled by the custom_block path instead.
 *
 * To add a new module card, register it in the federated block system — no bespoke
 * mappers here, no MessageList branches to grow.
 */
export type CardMapper = (data: any) => Message;

export const CARD_MAPPERS: Record<string, CardMapper> = {};

/** True for any WS message type this registry can render as a chat card. */
export function isCardType(type: string): boolean {
  return type in CARD_MAPPERS || type.endsWith('_card');
}

/** Map a card WS payload to a Message via the generic module-card mapper. */
export function mapCard(cardType: string, data: any): Message {
  const mapper = CARD_MAPPERS[cardType];
  return mapper ? mapper(data) : mapModuleCard(cardType, data);
}
