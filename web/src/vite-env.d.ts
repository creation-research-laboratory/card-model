/// <reference types="vite/client" />

/**
 * `bridge.py` is imported as text rather than fetched.
 *
 * Fetching it was a real bug: it lives in src/worker/, not public/, so the dev
 * server's SPA fallback answered `/bridge.py` with index.html and a 200, and
 * Pyodide reported a Python SyntaxError on `<title>`. Inlining removes the path
 * question entirely — the bundler hashes and ships the file wherever the worker
 * ends up — and saves a round trip.
 */
declare module "*.py?raw" {
  const source: string;
  export default source;
}
