import { describe, it, expect, beforeEach } from 'vitest';
import { useUiStore } from './ui';

describe('useUiStore', () => {
  beforeEach(() => {
    useUiStore.setState({
      sidebarCollapsed: false,
      mobileSidebarOpen: false,
      settingsModalOpen: false,
      commandPaletteOpen: false,
    });
  });

  it('toggles the sidebar', () => {
    useUiStore.getState().toggleSidebar();
    expect(useUiStore.getState().sidebarCollapsed).toBe(true);
  });

  it('opens and closes the settings modal', () => {
    useUiStore.getState().openSettingsModal();
    expect(useUiStore.getState().settingsModalOpen).toBe(true);
    useUiStore.getState().closeSettingsModal();
    expect(useUiStore.getState().settingsModalOpen).toBe(false);
  });

  it('toggles the mobile sidebar', () => {
    useUiStore.getState().toggleMobileSidebar();
    expect(useUiStore.getState().mobileSidebarOpen).toBe(true);
  });
});
