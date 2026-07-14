import { render, screen } from '@testing-library/react';
import { defineDashboard } from '../src/defineDashboard';

const Header = ({ apiBase }: { apiBase: string }) => <div>hdr:{apiBase}</div>;
const Jobs = ({ apiBase }: { apiBase: string }) => <div>jobs:{apiBase}</div>;
const Media = ({ apiBase }: { apiBase: string }) => <div>media:{apiBase}</div>;

const Dash = defineDashboard({
  title: 'T',
  header: Header,
  tabs: [
    { id: 'jobs', label: 'Jobs' },
    { id: 'media', label: 'Media' },
  ],
  panels: { jobs: Jobs, media: Media },
});

it('renders the panel for the active tab', () => {
  render(<Dash apiBase="/api" activeTab="media" />);
  expect(screen.getByText('media:/api')).toBeTruthy();
});

it('falls back to the first tab when activeTab is null or unknown', () => {
  const { rerender } = render(<Dash apiBase="/api" activeTab={null} />);
  expect(screen.getByText('jobs:/api')).toBeTruthy();
  rerender(<Dash apiBase="/api" activeTab="nope" />);
  expect(screen.getByText('jobs:/api')).toBeTruthy();
});

it('renders the persistent header slot', () => {
  render(<Dash apiBase="/api" activeTab="jobs" />);
  expect(screen.getByText('hdr:/api')).toBeTruthy();
});

it('exposes meta.tabs as {id,label}', () => {
  expect(Dash.meta.tabs).toEqual([
    { id: 'jobs', label: 'Jobs', icon: undefined },
    { id: 'media', label: 'Media', icon: undefined },
  ]);
});
