import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Development: `pnpm dev` serves the UI on :5180 and proxies /api to the Python server
// (`python -m maskserver --no-browser`, :8000). Production: `pnpm build` writes dist/,
// which maskserver serves itself.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    port: 5180,
    strictPort: true,
    proxy: { "/api": { target: "http://127.0.0.1:8000" } },
  },
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 1500,
    rolldownOptions: {
      output: {
        // Large libraries in their own long-cacheable chunks; panels load lazily (Workspace.tsx).
        codeSplitting: {
          groups: [
            { name: "react", test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
            { name: "echarts", test: /node_modules[\\/](echarts|zrender)[\\/]/ },
            { name: "ag-grid", test: /node_modules[\\/]ag-grid-(community|react)[\\/]/ },
            {
              name: "three",
              test: /node_modules[\\/](three|three-stdlib|@react-three|@monogrid|camera-controls|maath)[\\/]/,
            },
            { name: "dockview", test: /node_modules[\\/]dockview(-core|-react)?[\\/]/ },
          ],
        },
      },
    },
  },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
  },
});
