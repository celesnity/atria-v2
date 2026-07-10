import { describe, it, expect } from 'vitest';
import { CARD_MAPPERS, mapCard, isCardType } from './cardRegistry';

describe('cardRegistry (bespoke path removed)', () => {
  it('has no bespoke mappers', () => {
    expect(Object.keys(CARD_MAPPERS)).toHaveLength(0);
  });
  it('maps an unknown card_type via the generic module-card fallback', () => {
    const msg = mapCard('maintenance_answer', { answer: 'hi', confidence_band: 'high' });
    expect(msg.role).toBe('module_card');
    expect(msg.card_answer).toBe('hi');
  });
  it('recognises *_card types as cards', () => {
    expect(isCardType('foo_card')).toBe(true);
  });
});
