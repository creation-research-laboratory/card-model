/**
 * Boot Pyodide and expose `bridge.py` as callable functions.
 *
 * Environment-agnostic on purpose. The browser runs this inside a Web Worker;
 * the test suite runs it directly in Node against the same vendored files. That
 * is what makes the live path headlessly testable — otherwise "does the live
 * source agree with Python" could only be checked by driving a browser, and it
 * would not get checked.
 *
 * Resource loading is injected rather than assumed, because Node has no
 * `fetch`-from-disk and the browser has no `fs`.
 */

export interface RuntimeResources {
  /** Directory containing pyodide.asm.wasm, python_stdlib.zip, etc. */
  indexURL: string;
  /** The `card` wheel, as bytes. */
  loadWheel(): Promise<Uint8Array>;
  /** `bridge.py`, as source text. */
  loadBridge(): Promise<string>;
  /** Filename to mount the wheel under; must end in .whl. */
  wheelName?: string;
}

export interface BootTimings {
  loadPyodideMs: number;
  installWheelMs: number;
  importBridgeMs: number;
  totalMs: number;
}

export interface PyodideRuntime {
  call(fn: string, argJson?: string): string;
  timings: BootTimings;
  destroy(): void;
}

/**
 * A wheel is a zip and `card`'s model path is pure Python with no third-party
 * imports, so putting the wheel on `sys.path` *is* the installation. Measured
 * at ~3 ms. micropip would also work but pulls its own wheel plus a dependency
 * resolver with nothing to resolve.
 */
const INSTALL_VIA_ZIPIMPORT = true;

export async function createRuntime(
  resources: RuntimeResources,
): Promise<PyodideRuntime> {
  const wheelName = resources.wheelName ?? "card_model-0.1.0-py3-none-any.whl";
  const t0 = performance.now();

  // Imported dynamically so this module can be loaded (for its types) without
  // paying for the runtime.
  const { loadPyodide } = await import("pyodide");

  const t1 = performance.now();
  const pyodide = await loadPyodide({ indexURL: resources.indexURL });
  const loadPyodideMs = performance.now() - t1;

  const t2 = performance.now();
  const wheel = await resources.loadWheel();
  pyodide.FS.writeFile(`/${wheelName}`, wheel);
  if (INSTALL_VIA_ZIPIMPORT) {
    pyodide.runPython(`import sys; sys.path.insert(0, "/${wheelName}")`);
  }
  const installWheelMs = performance.now() - t2;

  const t3 = performance.now();
  pyodide.FS.writeFile("/bridge.py", await resources.loadBridge());
  pyodide.runPython(`import sys\nif "/" not in sys.path: sys.path.insert(0, "/")\nimport bridge`);
  const importBridgeMs = performance.now() - t3;

  const bridge = pyodide.globals.get("bridge");

  return {
    timings: {
      loadPyodideMs,
      installWheelMs,
      importBridgeMs,
      totalMs: performance.now() - t0,
    },
    call(fn: string, argJson?: string): string {
      // `boot` is a runtime concern, not a bridge function: it exists so a
      // caller can force initialization and learn what it cost without having
      // a model question to ask yet. Handled here rather than in the Worker so
      // both transports behave the same — the in-process one used by tests
      // included.
      if (fn === "boot") {
        return JSON.stringify({
          timings: {
            loadPyodideMs,
            installWheelMs,
            importBridgeMs,
            totalMs: performance.now() - t0,
          },
        });
      }
      const target = bridge[fn];
      if (typeof target !== "function") {
        throw new Error(`bridge.py has no function "${fn}"`);
      }
      return argJson === undefined ? target() : target(argJson);
    },
    destroy() {
      bridge.destroy();
    },
  };
}
