/**
 * Copy the Pyodide runtime out of node_modules into public/pyodide/.
 *
 * Vendored rather than loaded from a CDN: no third-party runtime dependency, no
 * CDN outage, a strict CSP with no script-src exceptions, and a build
 * reproducible from the lockfile. ~13 MB in the deploy artifact, against
 * GitHub Pages' 1 GB limit.
 *
 * Only five files are needed; the rest of the npm package is types, source maps
 * and a demo console.
 */
import { mkdirSync, copyFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = dirname(here);
const from = join(web, "node_modules", "pyodide");
const to = join(web, "public", "pyodide");

// pyodide.asm.mjs is the emscripten glue loaded by pyodide.mjs — it was
// pyodide.asm.js before 314.x, so re-check this list after a Pyodide upgrade.
const FILES = [
  "pyodide.mjs",
  "pyodide.asm.mjs",
  "pyodide.asm.wasm",
  "python_stdlib.zip",
  "pyodide-lock.json",
];

mkdirSync(to, { recursive: true });

let total = 0;
for (const name of FILES) {
  copyFileSync(join(from, name), join(to, name));
  const bytes = statSync(join(to, name)).size;
  total += bytes;
  console.log(`  ${name.padEnd(22)} ${(bytes / 1048576).toFixed(2)} MB`);
}
console.log(`  ${"TOTAL".padEnd(22)} ${(total / 1048576).toFixed(2)} MB uncompressed`);
