import { create } from 'zustand';
import type { EmbinderMotionMode } from '@embinder/react';

export type MascotMotionPreference = EmbinderMotionMode;

const STORAGE_KEY = 'minder-mascot-motion';

function readInitial(): MascotMotionPreference {
  if (typeof window === 'undefined') return 'system';
  const saved = window.localStorage.getItem(STORAGE_KEY);
  return saved === 'full' || saved === 'reduced' || saved === 'off' ? saved : 'system';
}

interface MascotMotionState {
  preference: MascotMotionPreference;
  setPreference: (preference: MascotMotionPreference) => void;
}

export const useMascotMotionStore = create<MascotMotionState>((set) => ({
  preference: readInitial(),
  setPreference: (preference) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, preference);
    } catch {
      /* Privacy mode and storage quota must not prevent an in-session preference update. */
    }
    set({ preference });
  },
}));
