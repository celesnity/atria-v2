import { describe, expect, it } from 'vitest';
import {
  callModuleEmbinderAction,
  getModuleEmbinderContext,
  publishModuleEmbinderContext,
  registerModuleEmbinderSurface,
} from './embinderModuleBridge';

describe('module Embinder bridge registry', () => {
  it('keeps module context and forwards an action to the registered surface', async () => {
    const unregister = registerModuleEmbinderSurface('embinder-test', async (action, args) => ({
      action,
      args,
    }));

    publishModuleEmbinderContext('embinder-test', { view: 'decisions' });
    expect(getModuleEmbinderContext('embinder-test')).toEqual({ view: 'decisions' });
    await expect(callModuleEmbinderAction('embinder-test', 'navigate', { section: 'today' }))
      .resolves.toEqual({ action: 'navigate', args: { section: 'today' } });

    unregister();
    expect(getModuleEmbinderContext('embinder-test')).toBeNull();
  });

  it('rejects actions for an unavailable module surface', async () => {
    await expect(callModuleEmbinderAction('missing-surface', 'inspect'))
      .rejects.toThrow('missing-surface is not open');
  });
});
