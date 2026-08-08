/**
 * Worker entry point. Boots the runtime lazily and forwards bridge calls.
 *
 * Kept to almost nothing: the runtime is in `pyodideRuntime.ts` so the test
 * suite can use it without a Worker, and all the model logic is in `card`.
 */

import { createRuntime, type PyodideRuntime } from "./pyodideRuntime.js";

let runtime: PyodideRuntime | null = null;
let booting: Promise<PyodideRuntime> | null = null;

async function ready(): Promise<PyodideRuntime> {
  if (runtime) return runtime;
  booting ??= createRuntime({
    indexURL: new URL("./pyodide/", self.location.href).href,
    wheelName: "card_model-0.1.0-py3-none-any.whl",
    async loadWheel() {
      const url = new URL("./card_model-0.1.0-py3-none-any.whl", self.location.href);
      const response = await fetch(url);
      if (!response.ok) throw new Error(`wheel: ${response.status} ${response.statusText}`);
      return new Uint8Array(await response.arrayBuffer());
    },
    async loadBridge() {
      const url = new URL("./bridge.py", self.location.href);
      const response = await fetch(url);
      if (!response.ok) throw new Error(`bridge.py: ${response.status} ${response.statusText}`);
      return response.text();
    },
  }).then((r) => (runtime = r));
  return booting;
}

self.onmessage = async (event: MessageEvent) => {
  const { id, fn, argJson } = event.data ?? {};
  try {
    const instance = await ready();
    // Including "boot", which the runtime handles — see pyodideRuntime.call.
    const result = instance.call(fn, argJson);
    (self as unknown as Worker).postMessage({ id, ok: true, result });
  } catch (error) {
    (self as unknown as Worker).postMessage({
      id, ok: false, error: error instanceof Error ? error.message : String(error),
    });
  }
};
