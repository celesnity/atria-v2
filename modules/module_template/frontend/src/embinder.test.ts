import { describe, expect, it } from 'vitest';
import { DEFAULT_TOKENS, normalizeDashboardProps } from './embinder';

describe('module-template Embinder adapter', () => {
  it('supplies stable tokens when the host provides no theme', () => {
    expect(DEFAULT_TOKENS.bg).toBe('#0b1020');
    expect(DEFAULT_TOKENS.primary).toBe('#2e6bf6');
  });

  it('normalizes optional host dashboard values', () => {
    expect(normalizeDashboardProps({})).toEqual({ apiBase: '', activeTab: undefined });
  });
});
