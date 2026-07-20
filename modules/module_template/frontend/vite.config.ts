import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { federation } from '@module-federation/vite';

const here = dirname(fileURLToPath(import.meta.url));
const embinder = resolve(here, '../../../minderSDK/packages/react/src');

// This dashboard is loaded as a cross-origin Module Federation remote: the host
// page (a different origin) pulls in remoteEntry.js from THIS module's server.
// The connector mounts our built `dist/` at `/dashboard/`, so any bundled asset
// (e.g. the mascot logo.png) must be referenced by a FULLY-QUALIFIED URL back to
// this module's own origin — a root-absolute `/assets/…` resolves against the
// HOST origin and 404s (the broken-mascot bug). `MT_PUBLIC_BASE` is this
// module's public origin; assets live under its `/dashboard/` mount.
const publicBase = (process.env.MT_PUBLIC_BASE || 'http://localhost:9300').replace(/\/$/, '');
const assetBase = `${publicBase}/dashboard/`;

export default defineConfig({
  experimental: {
    // `filename` is relative to outDir, e.g. "assets/logo-BxMuZe5m.png".
    renderBuiltUrl(filename) {
      return assetBase + filename;
    },
  },
  resolve: {
    alias: { '@embinder/react': resolve(embinder, 'index.ts') },
    dedupe: ['zod', 'react', 'react-dom'],
  },
  plugins: [
    react(),
    federation({
      name: 'module_template',
      filename: 'remoteEntry.js',
      dts: false,
      exposes: {
        './Dashboard': './src/dashboard.tsx',
        './ShowcaseBlock': './src/ShowcaseBlock.tsx',
      },
      shared: {
        react: { singleton: true, requiredVersion: '^18.3.1' },
        'react-dom': { singleton: true, requiredVersion: '^18.3.1' },
      },
    }),
  ],
  build: { outDir: 'dist', target: 'esnext' },
  server: { origin: 'http://localhost:9300' },
});
