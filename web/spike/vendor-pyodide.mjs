/**
 * Copy the Pyodide runtime out of node_modules into vendor/pyodide/.
 *
 * Production vendors the runtime rather than loading it from a CDN, so the
 * spike does too — the numbers only mean something if they measure the real
 * deployment path.  Vendoring buys a strict CSP with no script-src exceptions,
 * no third-party runtime dependency, and a build reproducible from the
 * lockfile.
 *
 * Only four files are needed.  Everything else in the npm package is types,
 * source maps and a demo console.
 */
import { mkdirSync, copyFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const from = join(here, "node_modules", "pyodide");
const to = join(here, "vendor", "pyodide");

// pyodide.asm.mjs is the emscripten glue loaded by pyodide.mjs (it was
// pyodide.asm.js before 314.x — check this list after a Pyodide upgrade);
// python_stdlib.zip is the standard library the interpreter mounts at boot;
// pyodide-lock.json is consulted even when no packages are loaded.
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
console.log(`  ${"TOTAL (uncompressed)".padEnd(22)} ${(total / 1048576).toFixed(2)} MB`);
