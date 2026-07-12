import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { federation } from '@module-federation/vite';
import { minderTabsSync } from '../../../minder_ui_sdk/src/vitePlugin';

const here = dirname(fileURLToPath(import.meta.url));
const sdk = resolve(here, '../../../minder_ui_sdk/src');

export default defineConfig({
  resolve: {
    alias: { 'minder-ui-sdk': resolve(sdk, 'index.ts') },
  },
  plugins: [
    react(),
    minderTabsSync(),
    federation({
      name: 'module_template',
      filename: 'remoteEntry.js',
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
