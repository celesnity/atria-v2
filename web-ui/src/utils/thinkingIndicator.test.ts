import { describe, it, expect } from 'vitest';
import { nextIndicatorState } from './thinkingIndicator';

describe('nextIndicatorState', () => {
  it('turns on when a turn starts', () => {
    expect(nextIndicatorState(false, 'start')).toBe(true);
  });
  it('turns off on the first streamed chunk', () => {
    expect(nextIndicatorState(true, 'chunk')).toBe(false);
  });
  it('turns off when tool activity arrives', () => {
    expect(nextIndicatorState(true, 'tool')).toBe(false);
  });
  it('turns off when the turn completes', () => {
    expect(nextIndicatorState(true, 'complete')).toBe(false);
  });
  it('stays off once cleared until the next start', () => {
    expect(nextIndicatorState(false, 'chunk')).toBe(false);
    expect(nextIndicatorState(false, 'tool')).toBe(false);
  });
});
