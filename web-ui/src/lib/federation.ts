import { registerRemotes, loadRemote } from '@module-federation/runtime';
import type { ComponentType } from 'react';

const registered = new Set<string>();

/** Idempotently register a module's federation remote by name + remoteEntry URL. */
export function registerRemote(opts: { name: string; entry: string }): void {
  if (registered.has(opts.name)) return;
  // type: 'module' — the connector's remoteEntry.js (built by @module-federation/vite)
  // is an ESM module, so the runtime must load it via import(), not a classic <script>
  // (which throws "Cannot use import statement outside a module").
  registerRemotes([{ name: opts.name, entry: opts.entry, type: 'module' }], { force: true });
  registered.add(opts.name);
}

/** Load an exposed module (e.g. './Dashboard') and return its default export. */
export async function loadRemoteComponent(
  name: string,
  exposed: string,
): Promise<ComponentType<any>> {
  const mod = (await loadRemote(`${name}/${exposed.replace(/^\.\//, '')}`)) as {
    default: ComponentType<any>;
  } | null;
  if (!mod || !mod.default) {
    throw new Error(`remote ${name}/${exposed} has no default export`);
  }
  return mod.default;
}
