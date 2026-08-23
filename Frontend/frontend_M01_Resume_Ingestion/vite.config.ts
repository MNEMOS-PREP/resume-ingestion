import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * M01 - Resume Ingestion & Claim Extraction, on its reserved port 5201 (PORTS.txt).
 *
 * This repo holds one module, so this is the app. When the platform shell
 * exists it mounts the same `src/routes.tsx` - the components are identical
 * either way, so what you fix here is what students get.
 */
const API_TARGET = process.env.VITE_API_BASE ?? "http://127.0.0.1:8101";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    // @ai/core ships TypeScript source rather than a build, so Vite must
    // transform it instead of pre-bundling it as an opaque dependency.
    exclude: ["@ai/core"],
  },
  server: {
    port: 5201,
    // Proxy to the M01 backend so the browser sees one origin and CORS never
    // comes up. Point at the platform gateway (:8000) instead by setting
    // VITE_API_BASE.
    proxy: {
      "/v1": { target: API_TARGET, changeOrigin: true },
      "/health": { target: API_TARGET, changeOrigin: true },
      // `/status` too. Without it the dev server answers with index.html and
      // a 200, so the Dependencies page's module-status query fails on JSON
      // parsing rather than on a status code — which reads as "the registry is
      // broken" instead of "this path is not proxied".
      "/status": { target: API_TARGET, changeOrigin: true },
    },
  },
  preview: { port: 5201 },
});
