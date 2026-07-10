import type { Message } from '../types';

/**
 * Derive a human-ish module name from a card_type. The connector default is
 * `"{module}_card"`, so strip a trailing `_card`; anything else is used as-is.
 */
export function moduleNameFromCardType(cardType: string): string {
  return cardType.endsWith('_card') ? cardType.slice(0, -'_card'.length) : cardType;
}

/**
 * Map a generic service-module card WS payload to a chat Message. Used for any
 * `card_type` that has no bespoke renderer registered — the payload shape is the
 * shared connector card contract (see atria/core/modules/remote.py), of which we
 * only surface the fields common to every module: answer text, confidence band,
 * and validation warnings. The full card is kept in `card_raw` for future use.
 */
export function mapModuleCard(cardType: string, d: any): Message {
  const answer = d.answer ?? '';
  return {
    role: 'module_card',
    content: answer,
    card_type: cardType,
    card_module: moduleNameFromCardType(cardType),
    card_answer: answer,
    card_confidence_band: d.confidence_band,
    card_validation_warnings: d.validation_warnings ?? [],
    card_raw: d,
    search_query: d.query,
    timestamp: new Date().toISOString(),
  };
}
