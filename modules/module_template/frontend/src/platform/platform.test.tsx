import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PlatformShell } from './PlatformShell';

describe('PlatformShell', () => {
  it('renders all four platform page controls and reports navigation', () => {
    const onNavigate = vi.fn();

    render(
      <PlatformShell activePage="mission-control" onNavigate={onNavigate}>
        <h1>Mission Control</h1>
      </PlatformShell>,
    );

    screen.getByRole('button', { name: /Incident & Data Analyst/ }).click();
    expect(onNavigate).toHaveBeenCalledWith('incident-analyst');
    expect(screen.getByRole('heading', { name: 'Mission Control' })).toBeTruthy();
  });
});
