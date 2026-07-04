import { describe, it, expect, beforeEach } from 'vitest';
import { useViewerTabsStore } from './viewerTabs';

beforeEach(() => {
  useViewerTabsStore.setState({ tabsByConv: {} });
});

describe('viewerTabs store', () => {
  it('opens a tab and sets it active', () => {
    useViewerTabsStore.getState().openTab('1', 'README.md');
    const { tabs, activeId } = useViewerTabsStore.getState().tabsByConv['1'];
    expect(tabs).toHaveLength(1);
    expect(tabs[0].kind === 'file' ? tabs[0].path : '').toBe('README.md');
    expect(activeId).toBe('README.md');
  });

  it('focuses existing tab on reopen instead of duplicating', () => {
    useViewerTabsStore.getState().openTab('1', 'a.txt');
    useViewerTabsStore.getState().openTab('1', 'b.txt');
    useViewerTabsStore.getState().openTab('1', 'a.txt');
    const { tabs, activeId } = useViewerTabsStore.getState().tabsByConv['1'];
    expect(tabs.map(t => (t.kind === 'file' ? t.path : ''))).toEqual(['a.txt', 'b.txt']);
    expect(activeId).toBe('a.txt');
  });

  it('closes the active tab and shifts active to neighbor', () => {
    useViewerTabsStore.getState().openTab('1', 'a.txt');
    useViewerTabsStore.getState().openTab('1', 'b.txt');
    useViewerTabsStore.getState().openTab('1', 'c.txt');
    useViewerTabsStore.getState().closeTab('1', 'b.txt');
    const { tabs, activeId } = useViewerTabsStore.getState().tabsByConv['1'];
    expect(tabs.map(t => (t.kind === 'file' ? t.path : ''))).toEqual(['a.txt', 'c.txt']);
    expect(activeId).toBe('c.txt');
  });

  it('closing the last tab leaves activeId null', () => {
    useViewerTabsStore.getState().openTab('1', 'only.txt');
    useViewerTabsStore.getState().closeTab('1', 'only.txt');
    const slice = useViewerTabsStore.getState().tabsByConv['1'];
    expect(slice.tabs).toEqual([]);
    expect(slice.activeId).toBeNull();
  });

  it('stores a reveal location when opening with one', () => {
    useViewerTabsStore.getState().openModuleFileTab(
      '1', 'maintenance_copilot', 'sample_manuals/amm.md',
      { text: 'Torque the pivot', nonce: 1 },
    );
    const tab = useViewerTabsStore.getState().tabsByConv['1'].tabs[0];
    expect(tab.kind === 'module-file' ? tab.location?.text : '').toBe('Torque the pivot');
  });

  it('re-opening the same tab updates the location and activates it', () => {
    const s = useViewerTabsStore.getState();
    s.openModuleFileTab('1', 'maintenance_copilot', 'a.md', { text: 'first', nonce: 1 });
    s.openTab('1', 'other.txt');
    useViewerTabsStore.getState().openModuleFileTab(
      '1', 'maintenance_copilot', 'a.md', { text: 'second', nonce: 2 },
    );
    const slice = useViewerTabsStore.getState().tabsByConv['1'];
    expect(slice.tabs).toHaveLength(2);
    expect(slice.activeId).toBe('module:maintenance_copilot:a.md');
    const tab = slice.tabs.find(t => t.id === 'module:maintenance_copilot:a.md')!;
    expect(tab.kind === 'module-file' ? tab.location?.text : '').toBe('second');
    expect(tab.kind === 'module-file' ? tab.location?.nonce : 0).toBe(2);
  });

  it('marks a tab dirty and clean', () => {
    useViewerTabsStore.getState().openTab('1', 'a.txt');
    expect(useViewerTabsStore.getState().tabsByConv['1'].dirty['a.txt']).toBeUndefined();

    useViewerTabsStore.getState().markDirty('1', 'a.txt');
    expect(useViewerTabsStore.getState().tabsByConv['1'].dirty['a.txt']).toBe(true);

    useViewerTabsStore.getState().markClean('1', 'a.txt');
    expect(useViewerTabsStore.getState().tabsByConv['1'].dirty['a.txt']).toBeUndefined();
  });

  it('keeps dirty flags independent across tabs', () => {
    useViewerTabsStore.getState().openTab('1', 'a.txt');
    useViewerTabsStore.getState().openTab('1', 'b.txt');
    useViewerTabsStore.getState().markDirty('1', 'a.txt');
    const { dirty } = useViewerTabsStore.getState().tabsByConv['1'];
    expect(dirty['a.txt']).toBe(true);
    expect(dirty['b.txt']).toBeUndefined();
  });

  it('clears the dirty flag when a tab is closed', () => {
    useViewerTabsStore.getState().openTab('1', 'a.txt');
    useViewerTabsStore.getState().openTab('1', 'b.txt');
    useViewerTabsStore.getState().markDirty('1', 'a.txt');
    useViewerTabsStore.getState().markDirty('1', 'b.txt');
    useViewerTabsStore.getState().closeTab('1', 'a.txt');
    const { dirty } = useViewerTabsStore.getState().tabsByConv['1'];
    expect(dirty['a.txt']).toBeUndefined();
    expect(dirty['b.txt']).toBe(true);
  });
});
