// @vitest-environment node
// esbuild's transformSync (used by extractTabsFromSource) requires the real
// Node TextEncoder; jsdom's global override trips esbuild's invariant check.
import {
  extractTabsFromSource,
  applyTabsToManifest,
  manifestTabsMatch,
} from '../src/manifestSync';

const SRC = `
export const TABS = [
  { id: 'jobs', label: 'Jobs', icon: 'briefcase' },
  { id: 'media', label: 'Media' },
] as const;
`;

it('extracts {id,label} from a plain TS tabs module', () => {
  expect(extractTabsFromSource(SRC)).toEqual([
    { id: 'jobs', label: 'Jobs' },
    { id: 'media', label: 'Media' },
  ]);
});

it('throws when the module does not export a TABS array', () => {
  expect(() => extractTabsFromSource('export const X = 1;')).toThrow();
});

it('merges dashboard.tabs while preserving every other manifest field', () => {
  const manifest = JSON.stringify(
    { display_name: 'Foo', dashboard: { title: 'D', badge_color: 'info' }, remote: { name: 'foo' } },
    null,
    2,
  );
  const out = applyTabsToManifest(manifest, [{ id: 'jobs', label: 'Jobs' }]);
  const parsed = JSON.parse(out);
  expect(parsed.dashboard.tabs).toEqual([{ id: 'jobs', label: 'Jobs' }]);
  expect(parsed.dashboard.title).toBe('D');
  expect(parsed.dashboard.badge_color).toBe('info');
  expect(parsed.remote.name).toBe('foo');
  expect(parsed.display_name).toBe('Foo');
  expect(out.endsWith('\n')).toBe(true);
});

it('creates dashboard when absent', () => {
  const out = applyTabsToManifest('{"display_name":"F"}', [{ id: 'a', label: 'A' }]);
  expect(JSON.parse(out).dashboard.tabs).toEqual([{ id: 'a', label: 'A' }]);
});

it('manifestTabsMatch reports equality by id+label', () => {
  const raw = JSON.stringify({ dashboard: { tabs: [{ id: 'a', label: 'A' }] } });
  expect(manifestTabsMatch(raw, [{ id: 'a', label: 'A' }])).toBe(true);
  expect(manifestTabsMatch(raw, [{ id: 'a', label: 'B' }])).toBe(false);
  expect(manifestTabsMatch('not json', [{ id: 'a', label: 'A' }])).toBe(false);
});
