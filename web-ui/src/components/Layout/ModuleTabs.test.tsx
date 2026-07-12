// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { ModuleTabs } from './ModuleTabs';
import { useModulesStore } from '../../stores/modules';

const mod = {
  name: 'plan', display_name: 'Plan', tooltip: 'Plan', icon_url: null,
  dashboard_title: 'Plan', dashboard_default_height: null, badge_color: null,
  remote: false, remote_name: null, remote_entry: null, remote_dashboard: null,
  api_base: null,
  tabs: [{ id: 'board', label: 'Board' }, { id: 'readiness', label: 'Readiness' }],
};

beforeEach(() => {
  useModulesStore.setState({
    modulesWithDashboards: [mod], activeModuleDashboard: 'plan', activeModuleTab: 'board',
  });
});

afterEach(() => {
  cleanup();
});

describe('ModuleTabs', () => {
  it('renders the active module tabs with active marker', () => {
    render(<ModuleTabs />);
    expect(screen.getByRole('button', { name: 'Board' }).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('button', { name: 'Readiness' }).getAttribute('aria-current')).toBeNull();
  });

  it('clicking a tab calls setModuleTab', () => {
    render(<ModuleTabs />);
    fireEvent.click(screen.getByRole('button', { name: 'Readiness' }));
    expect(useModulesStore.getState().activeModuleTab).toBe('readiness');
  });

  it('renders nothing when no module is selected', () => {
    useModulesStore.setState({ activeModuleDashboard: null, activeModuleTab: null });
    const { container } = render(<ModuleTabs />);
    expect(container.firstChild).toBeNull();
  });
});
