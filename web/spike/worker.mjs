/**
 * Pyodide in a Web Worker.
 *
 * The worker is not an optimization — it is the difference between a usable
 * page and a frozen one.  Booting the interpreter on the main thread blocks
 * paint and input for seconds, and every later solve would jank a dragged
 * slider.  Off-thread, the page is interactive from t=0 and the boot cost is
 * paid in the background.
 *
 * The card wheel is installed by *zipimport*, not micropip.  A wheel is a zip,
 * and `card` is pure Python with no dependencies its model path needs, so
 * putting the wheel on sys.path is enough.  micropip would work but pulls its
 * own wheel and a dependency resolver we have nothing to resolve — pure cost.
 */

let pyodide = null;
const timings = {};

async function boot() {
  const t0 = performance.now();

  const { loadPyodide } = await import("./vendor/pyodide/pyodide.mjs");
  timings.import_loader_ms = performance.now() - t0;

  const t1 = performance.now();
  pyodide = await loadPyodide({ indexURL: "./vendor/pyodide/" });
  timings.load_pyodide_ms = performance.now() - t1;

  // --- install the card wheel -------------------------------------------
  const t2 = performance.now();
  const wheelName = "card_model-0.1.0-py3-none-any.whl";
  const wheelBytes = new Uint8Array(
    await (await fetch(`./vendor/${wheelName}`)).arrayBuffer()
  );
  pyodide.FS.writeFile(`/${wheelName}`, wheelBytes);
  pyodide.runPython(`
import sys
sys.path.insert(0, "/${wheelName}")
`);
  timings.install_wheel_ms = performance.now() - t2;

  // --- load the bridge ---------------------------------------------------
  const t3 = performance.now();
  const bridgeSource = await (await fetch("./bridge.py")).text();
  pyodide.FS.writeFile("/bridge.py", bridgeSource);
  pyodide.runPython(`
import sys
sys.path.insert(0, "/")
import bridge
`);
  timings.import_bridge_ms = performance.now() - t3;

  timings.total_boot_ms = performance.now() - t0;

  // The runtime, the stdlib and the wheel are all fetched by the worker, so
  // the page's own Resource Timing buffer never sees them — measuring payload
  // from the main thread reports ~0 and looks like a win that isn't real.
  timings.resources = performance.getEntriesByType("resource").map((r) => ({
    name: r.name.split("/").pop(),
    transfer: r.transferSize,
    decoded: r.decodedBodySize,
    // Kept so effective throughput can be computed rather than assumed: a
    // throttle's nominal rate and what it actually delivers are not the same
    // number, and the payload cost has to be quoted against a measured rate.
    start: r.startTime,
    end: r.responseEnd,
  }));
  return timings;
}

function call(fn, argJson) {
  const bridge = pyodide.globals.get("bridge");
  const result = argJson === undefined
    ? bridge[fn]()
    : bridge[fn](argJson);
  bridge.destroy();
  return JSON.parse(result);
}

self.onmessage = async (event) => {
  const { id, type, payload } = event.data;
  try {
    let result;
    if (type === "boot") {
      result = await boot();
    } else if (type === "environment") {
      result = call("environment");
    } else if (type === "calibrate") {
      const started = performance.now();
      result = call("calibrate", JSON.stringify(payload));
      result.round_trip_ms = performance.now() - started;
    } else if (type === "series") {
      const started = performance.now();
      result = call("series", JSON.stringify(payload));
      result.round_trip_ms = performance.now() - started;
    } else {
      throw new Error(`unknown message type: ${type}`);
    }
    self.postMessage({ id, ok: true, result });
  } catch (error) {
    self.postMessage({ id, ok: false, error: String(error) });
  }
};
