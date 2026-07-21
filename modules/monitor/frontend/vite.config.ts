import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { federation } from "@module-federation/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { minderTabsSync } from "../../../minder_ui_sdk/src/vitePlugin";

const here = dirname(fileURLToPath(import.meta.url));
const sdk = resolve(here, "../../../minder_ui_sdk/src");
const publicBase = (process.env.MONITOR_PUBLIC_BASE || "http://localhost:9310").replace(/\/$/, "");
const assetBase = `${publicBase}/dashboard/`;

export default defineConfig({
  base: "/dashboard/",
  experimental: {
    renderBuiltUrl(filename) {
      return assetBase + filename;
    },
  },
  resolve: {
    alias: { "minder-ui-sdk": resolve(sdk, "index.ts") },
    dedupe: ["zod", "fast-json-patch", "react", "react-dom"],
  },
  plugins: [
    react(),
    minderTabsSync(),
    federation({
      name: "monitor",
      dts: false,
      filename: "remoteEntry.js",
      exposes: { "./Dashboard": "./src/dashboard.tsx" },
      shared: {
        react: { singleton: true, requiredVersion: "^18.3.1" },
        "react-dom": { singleton: true, requiredVersion: "^18.3.1" },
      },
    }),
  ],
  build: { outDir: "dist", target: "esnext" },
  server: { origin: "http://localhost:9310", port: 9311 },
});
