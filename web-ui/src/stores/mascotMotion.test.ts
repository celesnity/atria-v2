import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useMascotMotionStore } from './mascotMotion';

describe('useMascotMotionStore', () => {
  const saved = new Map<string, string>();

  beforeEach(() => {
    saved.clear();
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key: string) => saved.get(key) ?? null,
        setItem: (key: string, value: string) => saved.set(key, value),
      },
    });
    useMascotMotionStore.setState({ preference: 'system' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('keeps the selected mascot motion mode for the next visit', () => {
    useMascotMotionStore.getState().setPreference('full');

    expect(useMascotMotionStore.getState().preference).toBe('full');
    expect(saved.get('minder-mascot-motion')).toBe('full');
  });
});
