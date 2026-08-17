import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Phase 3 has no app UI — index.html is a developer harness that exercises the
// model layer in a real browser. Phase 4 replaces it with the actual app.
//
// `base` matters for deployment: the app is mounted at /card-model/app/ inside
// the mkdocs site, because GitHub Pages allows one site per repo and docs.yml
// already owns it.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE ?? "/",
  publicDir: "public",
  server: {
    port: 8423,
    // The vendored runtime is ~13 MB of static files; don't let the dev server
    // try to pre-bundle or transform them.
    fs: { strict: false },
  },
  worker: {
    format: "es",
  },
  build: {
    rollupOptions: {
      // harness.html is dev scaffolding, but it is the only thing that
      // exercises the Worker path in a browser, so it ships alongside the app.
      input: { app: "index.html", harness: "harness.html" },
    },
  },
  optimizeDeps: {
    // Pyodide is loaded by the worker from public/, not bundled.
    exclude: ["pyodide"],
  },
});
