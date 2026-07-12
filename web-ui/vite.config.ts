import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { federation } from '@module-federation/vite'

// Get backend URL from environment or default to the backend's IPv4 bind.
// Use 127.0.0.1 (not "localhost"): on Windows "localhost" resolves to IPv6
// ::1 first, but run-backend.ps1 binds 127.0.0.1 only, so a localhost target
// makes Node's proxy log AggregateError [ECONNREFUSED] on the ::1 attempt.
const apiUrl = process.env.VITE_API_URL || 'http://127.0.0.1:8080';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    federation({
      name: 'minder_host',
      // No static remotes — service-modules are registered at RUNTIME (Task 3.2)
      // from their connector manifests. This keeps the host decoupled from any
      // specific module at build time.
      remotes: {},
      shared: {
        react: { singleton: true, requiredVersion: '^18.3.1' },
        'react-dom': { singleton: true, requiredVersion: '^18.3.1' },
      },
      filename: 'remoteEntry.js',
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false, // Allow Vite to try next port if 5173 is busy
    proxy: {
      '/api': {
        target: apiUrl,
        changeOrigin: true,
      },
      '/ws': {
        target: apiUrl.replace('http', 'ws'),
        ws: true,
        changeOrigin: true,
        // Add logging to debug proxy
        configure: (proxy, _options) => {
          proxy.on('proxyReq', (proxyReq, req, _res) => {
            console.log('[Vite Proxy] Forwarding WebSocket:', req.url, 'to', apiUrl);
          });
        },
      },
    },
  },
  build: {
    outDir: '../minder/web/static',
    emptyOutDir: true,
    // Module Federation manages chunk splitting; a manualChunks map here is
    // ignored by the plugin. Rely on dynamic import() splits (viewers are lazy).
  },
})
