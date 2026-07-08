import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Get backend URL from environment or default to the backend's IPv4 bind.
// Use 127.0.0.1 (not "localhost"): on Windows "localhost" resolves to IPv6
// ::1 first, but run-backend.ps1 binds 127.0.0.1 only, so a localhost target
// makes Node's proxy log AggregateError [ECONNREFUSED] on the ::1 attempt.
const apiUrl = process.env.VITE_API_URL || 'http://127.0.0.1:8080';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
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
    outDir: '../atria/web/static',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Split heavy deps into their own chunks so they're fetched on-demand,
        // not blocking the editorial Login/Landing hero on cold start.
        manualChunks: {
          'chart-vendor': ['recharts'],
          'markdown-vendor': ['react-markdown'],
          'motion-vendor': ['motion', 'animejs'],
          'monaco-vendor': ['@monaco-editor/react', 'monaco-editor'],
          'xlsx-vendor': ['xlsx'],
        },
      },
    },
  },
})
