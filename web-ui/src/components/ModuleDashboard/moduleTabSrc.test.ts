import { describe, it, expect } from 'vitest';
import { moduleTabSrc } from './ModuleDashboardView';

describe('moduleTabSrc', () => {
  it('no tab -> base dashboard.html', () => {
    expect(moduleTabSrc('plan', null)).toBe('/api/modules/plan/dashboard.html');
  });
  it('tab with entry -> that entry file', () => {
    expect(moduleTabSrc('plan', { id: 'r', label: 'R', entry: 'readiness.html' }))
      .toBe('/api/modules/plan/readiness.html');
  });
  it('tab without entry -> hash mode on dashboard.html', () => {
    expect(moduleTabSrc('plan', { id: 'scenarios', label: 'S' }))
      .toBe('/api/modules/plan/dashboard.html#scenarios');
  });
  it('encodes the module name', () => {
    expect(moduleTabSrc('a b', null)).toBe('/api/modules/a%20b/dashboard.html');
  });
});
