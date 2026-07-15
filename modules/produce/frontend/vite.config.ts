import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { federation } from '@module-federation/vite';
import { minderTabsSync } from '../../../minder_ui_sdk/src/vitePlugin';

const here = dirname(fileURLToPath(import.meta.url));
const sdk = resolve(here, '../../../minder_ui_sdk/src');

// Federation remote is served cross-origin by the host; bundled asset URLs must
// be fully-qualified back to THIS module's public origin.
const publicBase = (process.env.PR_PUBLIC_BASE || 'http://localhost:9310').replace(/\/$/, '');
const assetBase = `${publicBase}/dashboard/`;

export default defineConfig({
  experimental: {
    renderBuiltUrl(filename) {
      return assetBase + filename;
    },
  },
  resolve: {
    alias: { 'minder-ui-sdk': resolve(sdk, 'index.ts') },
  },
  plugins: [
    react(),
    minderTabsSync(),
    federation({
      name: 'produce',
      filename: 'remoteEntry.js',
      exposes: { './Dashboard': './src/dashboard.tsx' },
      shared: {
        react: { singleton: true, requiredVersion: '^18.3.1' },
        'react-dom': { singleton: true, requiredVersion: '^18.3.1' },
      },
    }),
  ],
  build: { outDir: 'dist', target: 'esnext' },
  server: { origin: 'http://localhost:9310', port: 5173 },
});
