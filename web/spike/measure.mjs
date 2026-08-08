/**
 * Headless measurement harness — the same boot path, run repeatedly.
 *
 * The browser page is the authority on payload and on "does this work in a
 * real browser at all".  It is a poor instrument for *timing statistics*,
 * because each run needs a fresh tab and the numbers move with whatever else
 * the browser is doing.  Pyodide runs under Node from the same vendored files,
 * so this measures the identical boot sequence N times and reports a
 * distribution instead of an anecdote.
 *
 * What this does NOT measure, by construction: wasm streaming compilation over
 * HTTP, transfer sizes, and Worker overhead.  Take those from the browser run.
 *
 *   node measure.mjs [runs]
 */
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const RUNS = Number(process.argv[2] || 5);
const WHEEL = "card_model-0.1.0-py3-none-any.whl";

// Pinned from the Python package: the browser must agree with the interpreter,
// not merely produce a number.
const EXPECTED = { lambda_F: 318754, k_F: 0.00482991 };

const SPEC = JSON.stringify({
  chronology: { age_of_earth: 6056, flood_start_date: 1656,
                flood_end_date: 1656, ice_age_end_date: 3500 },
  flood_secular_age: 66.0e6,
  second_secular_age: 11500,
});

async function once() {
  const t = {};
  const t0 = performance.now();

  const { loadPyodide } = await import("./node_modules/pyodide/pyodide.mjs");
  t.import_loader_ms = performance.now() - t0;

  const t1 = performance.now();
  const pyodide = await loadPyodide({
    indexURL: join(here, "node_modules", "pyodide"),
  });
  t.load_pyodide_ms = performance.now() - t1;

  const t2 = performance.now();
  const wheel = await readFile(join(here, "vendor", WHEEL));
  pyodide.FS.writeFile(`/${WHEEL}`, new Uint8Array(wheel));
  // A wheel is a zip and `card`'s model path is pure Python with no third-party
  // imports, so zipimport is the whole installation step.  micropip would work
  // but adds its own wheel plus a resolver with nothing to resolve.
  pyodide.runPython(`import sys; sys.path.insert(0, "/${WHEEL}")`);
  t.install_wheel_ms = performance.now() - t2;

  const t3 = performance.now();
  const bridge = await readFile(join(here, "bridge.py"), "utf8");
  pyodide.FS.writeFile("/bridge.py", bridge);
  pyodide.runPython(`import sys; sys.path.insert(0, "/"); import bridge`);
  t.import_bridge_ms = performance.now() - t3;

  t.total_boot_ms = performance.now() - t0;

  const py = pyodide.globals.get("bridge");
  const env = JSON.parse(py.environment());
  const first = JSON.parse(py.calibrate(SPEC));

  // Steady state, after the first call has warmed everything up.
  const solves = [];
  for (let i = 0; i < 20; i++) solves.push(JSON.parse(py.calibrate(SPEC)).solve_ms);
  const series = JSON.parse(py.series(JSON.stringify({ ...JSON.parse(SPEC), n: 400 })));
  py.destroy();

  return { t, env, first, solves, series };
}

const median = (a) => a.slice().sort((x, y) => x - y)[Math.floor(a.length / 2)];
const stats = (a) => ({
  min: Math.min(...a), median: median(a), max: Math.max(...a),
});
const fmt = (n, d = 1) => Number(n).toFixed(d);

console.log(`Pyodide boot measurement — ${RUNS} runs\n`);

const boots = [], loads = [], wheels = [], steadies = [], seriesTimes = [];
let env = null, first = null, failures = 0;

for (let i = 0; i < RUNS; i++) {
  try {
    const r = await once();
    boots.push(r.t.total_boot_ms);
    loads.push(r.t.load_pyodide_ms);
    wheels.push(r.t.install_wheel_ms);
    steadies.push(median(r.solves));
    seriesTimes.push(r.series.series_ms);
    env = r.env; first = r.first;
    console.log(`  run ${i + 1}: boot ${fmt(r.t.total_boot_ms)} ms, ` +
                `steady solve ${fmt(median(r.solves), 2)} ms`);
  } catch (error) {
    failures++;
    console.log(`  run ${i + 1}: FAILED — ${error.message}`);
  }
}

const relL = Math.abs(first.lambda_F / EXPECTED.lambda_F - 1);
const relK = Math.abs(first.k_F / EXPECTED.k_F - 1);

console.log(`
─────────────────────────────────────────────────────────
  runs completed          ${RUNS - failures}/${RUNS}${failures ? "  <-- FAILURES" : ""}

  BOOT (cold interpreter, warm file cache)
  total                   min ${fmt(stats(boots).min)}  median ${fmt(stats(boots).median)}  max ${fmt(stats(boots).max)} ms
  of which loadPyodide    min ${fmt(stats(loads).min)}  median ${fmt(stats(loads).median)}  max ${fmt(stats(loads).max)} ms
  of which wheel install  median ${fmt(stats(wheels).median, 2)} ms

  STEADY STATE
  solve_flood_only        median ${fmt(stats(steadies).median, 2)} ms
  400-point series        median ${fmt(stats(seriesTimes).median, 2)} ms
  frame budget @60fps     16.7 ms

  ENVIRONMENT
  python                  ${env.python}
  card                    ${env.card_version}
  numpy loaded            ${env.numpy_loaded}
  scipy loaded            ${env.scipy_loaded}
  stdlib-only             ${!env.numpy_loaded && !env.scipy_loaded ? "CONFIRMED" : "VIOLATED"}

  CORRECTNESS vs the Python package
  lambda_F                ${first.lambda_F.toPrecision(9)}  (expected ~${EXPECTED.lambda_F})
  k_F                     ${first.k_F.toPrecision(9)}  (expected ~${EXPECTED.k_F})
  agreement               ${relL < 1e-5 && relK < 1e-5 ? "matches to <1e-5" : "MISMATCH"}
  max |residual|          ${first.max_abs_residual.toExponential(2)}
─────────────────────────────────────────────────────────`);

process.exit(failures ? 1 : 0);
