import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Plugin } from 'vite';
import { extractTabsFromSource, applyTabsToManifest, manifestTabsMatch } from './manifestSync';

export interface MinderTabsSyncOptions {
  /** TS module exporting `const TABS`. Relative to the vite root. */
  tabsSource?: string;
  /** Module manifest.json to update. Relative to the vite root. */
  manifestPath?: string;
}

/**
 * Vite plugin: keep `manifest.json`'s `dashboard.tabs` in sync with the module's
 * `src/dashboard.tabs.ts`, so the Minder host top-bar shows the right tabs. Fails
 * soft — a missing/broken manifest logs a warning, never breaks the build.
 */
export function minderTabsSync(options: MinderTabsSyncOptions = {}): Plugin {
  const tabsSource = options.tabsSource ?? 'src/dashboard.tabs.ts';
  const manifestPath = options.manifestPath ?? '../manifest.json';
  let root = process.cwd();

  const sync = (warn: (m: string) => void): void => {
    try {
      const tabs = extractTabsFromSource(readFileSync(resolve(root, tabsSource), 'utf8'));
      const mf = resolve(root, manifestPath);
      const raw = readFileSync(mf, 'utf8');
      if (manifestTabsMatch(raw, tabs)) return;
      writeFileSync(mf, applyTabsToManifest(raw, tabs));
      warn(`minder-tabs-sync: wrote ${tabs.length} tab(s) → ${manifestPath}`);
    } catch (e) {
      warn(`minder-tabs-sync: skipped — ${(e as Error).message}`);
    }
  };

  return {
    name: 'minder-tabs-sync',
    configResolved(config) {
      root = config.root;
    },
    buildStart() {
      sync((m) => this.warn(m));
    },
    configureServer(server) {
      const warn = (m: string) => server.config.logger.warn(m);
      sync(warn);
      const abs = resolve(root, tabsSource);
      server.watcher.add(abs);
      server.watcher.on('change', (f) => {
        if (resolve(f) === abs) sync(warn);
      });
    },
  };
}
