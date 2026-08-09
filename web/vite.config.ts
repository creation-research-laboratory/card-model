import { defineConfig } from "vite";

// Phase 3 has no app UI — index.html is a developer harness that exercises the
// model layer in a real browser. Phase 4 replaces it with the actual app.
//
// `base` matters for deployment: the app is mounted at /card-model/app/ inside
// the mkdocs site, because GitHub Pages allows one site per repo and docs.yml
// already owns it.
export default defineConfig({
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
  optimizeDeps: {
    // Pyodide is loaded by the worker from public/, not bundled.
    exclude: ["pyodide"],
  },
});
