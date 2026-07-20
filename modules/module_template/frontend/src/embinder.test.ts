import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { DEFAULT_TOKENS, normalizeDashboardProps } from './embinder';

describe('module-template Embinder adapter', () => {
  it('supplies stable tokens when the host provides no theme', () => {
    expect(DEFAULT_TOKENS.bg).toBe('#0b1020');
    expect(DEFAULT_TOKENS.primary).toBe('#2e6bf6');
  });

  it('normalizes optional host dashboard values', () => {
    expect(normalizeDashboardProps({})).toEqual({ apiBase: '', activeTab: undefined });
  });

  it('uses a valid scope name and never mounts the relay-backed provider', () => {
    const dashboard = readFileSync(new URL('./dashboard.tsx', import.meta.url), 'utf8');
    const adapter = readFileSync(new URL('./embinder.tsx', import.meta.url), 'utf8');

    expect(dashboard).toContain('name="module_template"');
    expect(adapter).not.toContain('<Embind' + 'erProvider');
  });
});
