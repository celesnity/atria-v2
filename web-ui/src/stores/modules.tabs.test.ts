import { describe, it, expect, beforeEach } from 'vitest';
import { useModulesStore } from './modules';
import type { ModuleSummary } from './modules';

const withTabs: ModuleSummary = {
  name: 'plan', display_name: 'Plan', tooltip: 'Plan', icon_url: null,
  dashboard_title: 'Plan', dashboard_default_height: null, badge_color: null,
  remote: false, remote_name: null, remote_entry: null, remote_dashboard: null,
  api_base: null,
  tabs: [
    { id: 'board', label: 'Board', entry: 'dashboard.html' },
    { id: 'readiness', label: 'Readiness' },
  ],
};
const noTabs: ModuleSummary = { ...withTabs, name: 'legacy', tabs: [] };

beforeEach(() => {
  useModulesStore.setState({
    modulesWithDashboards: [withTabs, noTabs],
    activeModuleDashboard: null,
    activeModuleTab: null,
  });
});

describe('modules store tabs', () => {
  it('openDashboard resets to the first tab', () => {
    useModulesStore.getState().openDashboard('plan');
    expect(useModulesStore.getState().activeModuleTab).toBe('board');
  });

  it('openDashboard on a no-tabs module leaves activeModuleTab null', () => {
    useModulesStore.getState().openDashboard('legacy');
    expect(useModulesStore.getState().activeModuleTab).toBeNull();
  });

  it('setModuleTab changes the active tab', () => {
    useModulesStore.getState().openDashboard('plan');
    useModulesStore.getState().setModuleTab('readiness');
    expect(useModulesStore.getState().activeModuleTab).toBe('readiness');
  });

  it('closeDashboard clears the active tab', () => {
    useModulesStore.getState().openDashboard('plan');
    useModulesStore.getState().closeDashboard();
    expect(useModulesStore.getState().activeModuleTab).toBeNull();
  });
});
