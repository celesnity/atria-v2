import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { federation } from '@module-federation/vite';

export default defineConfig({
  plugins: [
    react(),
    federation({
      name: 'maintenance_copilot',
      filename: 'remoteEntry.js',
      exposes: {
        './Dashboard': './src/DashboardApp.tsx',
        './MaintenanceAnswer': './src/MaintenanceAnswer.tsx',
      },
      shared: {
        react: { singleton: true, requiredVersion: '^18.3.1' },
        'react-dom': { singleton: true, requiredVersion: '^18.3.1' },
      },
    }),
  ],
  build: {
    outDir: 'dist',
    target: 'esnext',
  },
  server: { origin: 'http://localhost:9200' },
});
