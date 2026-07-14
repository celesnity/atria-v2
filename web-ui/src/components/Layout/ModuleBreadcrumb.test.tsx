// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { ModuleBreadcrumb } from './ModuleBreadcrumb';
import { useModulesStore } from '../../stores/modules';

const base = {
  tooltip: '', icon_url: null, dashboard_title: '', dashboard_default_height: null,
  badge_color: null, remote: false, remote_name: null, remote_entry: null,
  remote_dashboard: null, api_base: null, tabs: [] as { id: string; label: string }[],
};

beforeEach(() => {
  useModulesStore.setState({
    modulesWithDashboards: [
      { ...base, name: 'plan', display_name: 'Plan' },
      { ...base, name: 'move', display_name: 'Move' },
    ],
    activeModuleDashboard: 'plan', activeModuleTab: null,
  });
});

afterEach(cleanup);

describe('ModuleBreadcrumb', () => {
  it('shows the active module name', () => {
    render(<ModuleBreadcrumb />);
    expect(screen.getByRole('button', { name: /Plan/ })).toBeTruthy();
  });

  it('opens the dropdown and selects another module', () => {
    render(<ModuleBreadcrumb />);
    fireEvent.click(screen.getByRole('button', { name: /Plan/ }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Move/ }));
    expect(useModulesStore.getState().activeModuleDashboard).toBe('move');
  });
});
