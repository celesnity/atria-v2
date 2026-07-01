import { create } from 'zustand';
import type { ViewerTab } from '../types';

interface TabSlice {
  tabs: ViewerTab[];
  activeId: string | null;
  dirty: Record<string, boolean>;
}

interface ViewerTabsState {
  tabsByConv: Record<string, TabSlice>;
  openTab: (convId: string, path: string) => void;
  openModuleTab: (convId: string, name: string) => void;
  openModuleFileTab: (convId: string, module: string, path: string) => void;
  closeTab: (convId: string, id: string) => void;
  setActive: (convId: string, id: string) => void;
  markDirty: (convId: string, id: string) => void;
  markClean: (convId: string, id: string) => void;
  clearConv: (convId: string) => void;
}

function extOf(path: string): { name: string; ext: string } {
  const name = path.split('/').pop() || path;
  const dot = name.lastIndexOf('.');
  const ext = dot >= 0 ? name.slice(dot).toLowerCase() : '';
  return { name, ext };
}

function tabFromPath(path: string): ViewerTab {
  const { name, ext } = extOf(path);
  return { kind: 'file', id: path, path, name, ext };
}

function tabFromModule(name: string): ViewerTab {
  return { kind: 'module', id: `module:${name}`, name };
}

function tabFromModuleFile(module: string, path: string): ViewerTab {
  const { name, ext } = extOf(path);
  return {
    kind: 'module-file',
    id: `module:${module}:${path}`,
    module,
    path,
    name,
    ext,
  };
}

function openTabIn(slice: TabSlice, tab: ViewerTab): TabSlice {
  const existing = slice.tabs.find(t => t.id === tab.id);
  if (existing) return { ...slice, activeId: tab.id };
  return { tabs: [...slice.tabs, tab], activeId: tab.id, dirty: slice.dirty };
}

export const useViewerTabsStore = create<ViewerTabsState>((set, get) => ({
  tabsByConv: {},

  openTab: (convId, path) => {
    const slice = get().tabsByConv[convId] ?? { tabs: [], activeId: null, dirty: {} };
    set({ tabsByConv: { ...get().tabsByConv, [convId]: openTabIn(slice, tabFromPath(path)) } });
  },

  openModuleTab: (convId, name) => {
    const slice = get().tabsByConv[convId] ?? { tabs: [], activeId: null, dirty: {} };
    set({ tabsByConv: { ...get().tabsByConv, [convId]: openTabIn(slice, tabFromModule(name)) } });
  },

  openModuleFileTab: (convId, module, path) => {
    const slice = get().tabsByConv[convId] ?? { tabs: [], activeId: null, dirty: {} };
    set({
      tabsByConv: {
        ...get().tabsByConv,
        [convId]: openTabIn(slice, tabFromModuleFile(module, path)),
      },
    });
  },

  closeTab: (convId, id) => {
    const slice = get().tabsByConv[convId];
    if (!slice) return;
    const idx = slice.tabs.findIndex(t => t.id === id);
    if (idx < 0) return;
    const remaining = slice.tabs.filter(t => t.id !== id);
    let nextActive: string | null = slice.activeId;
    if (slice.activeId === id) {
      if (remaining.length === 0) nextActive = null;
      else nextActive = remaining[Math.min(idx, remaining.length - 1)].id;
    }
    const { [id]: _removed, ...dirty } = slice.dirty;
    set({
      tabsByConv: {
        ...get().tabsByConv,
        [convId]: { tabs: remaining, activeId: nextActive, dirty },
      },
    });
  },

  setActive: (convId, id) => {
    const slice = get().tabsByConv[convId];
    if (!slice || !slice.tabs.some(t => t.id === id)) return;
    set({ tabsByConv: { ...get().tabsByConv, [convId]: { ...slice, activeId: id } } });
  },

  markDirty: (convId, id) => {
    const slice = get().tabsByConv[convId];
    if (!slice) return;
    if (slice.dirty[id]) return;
    set({
      tabsByConv: {
        ...get().tabsByConv,
        [convId]: { ...slice, dirty: { ...slice.dirty, [id]: true } },
      },
    });
  },

  markClean: (convId, id) => {
    const slice = get().tabsByConv[convId];
    if (!slice || !slice.dirty[id]) return;
    const { [id]: _removed, ...dirty } = slice.dirty;
    set({ tabsByConv: { ...get().tabsByConv, [convId]: { ...slice, dirty } } });
  },

  clearConv: (convId) => {
    const rest = { ...get().tabsByConv };
    delete rest[convId];
    set({ tabsByConv: rest });
  },
}));
