/**
 * Worker entry point. Boots the runtime lazily and forwards bridge calls.
 *
 * Kept to almost nothing: the runtime is in `pyodideRuntime.ts` so the test
 * suite can use it without a Worker, and all the model logic is in `card`.
 *
 * Asset paths come from an `init` message rather than being resolved against
 * this module's own URL. The worker does not live where its assets do: in dev
 * it is served from /src/worker/, in production it is a hashed bundle, and the
 * app deploys under a subpath (/card-model/app/). Resolving relatively would
 * be wrong in all three.
 */

import { createRuntime, type PyodideRuntime } from "./pyodideRuntime.js";

// Inlined by the bundler rather than fetched. bridge.py lives in src/, not
// public/, so a fetch of "./bridge.py" hit the dev server's SPA fallback and
// got index.html back with a 200 — Pyodide then reported a Python SyntaxError
// on `<title>`. Inlining removes the path question and a round trip.
import bridgeSource from "./bridge.py?raw";

let runtime: PyodideRuntime | null = null;
let booting: Promise<PyodideRuntime> | null = null;
let baseUrl: string | null = null;

const WHEEL = "card_model-0.1.0-py3-none-any.whl";

async function fetchOrThrow(url: URL): Promise<Response> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url.pathname}: ${response.status} ${response.statusText}`);
  }
  // A dev server or a 404 page that answers 200 with HTML is the failure above,
  // and it surfaces deep inside Pyodide as something unrecognizable. Catch it
  // where the cause is still obvious.
  const type = response.headers.get("content-type") ?? "";
  if (type.includes("text/html")) {
    throw new Error(
      `${url.pathname} returned HTML, not the expected asset — it is probably ` +
      "not being served from the app's base URL.",
    );
  }
  return response;
}

async function ready(): Promise<PyodideRuntime> {
  if (runtime) return runtime;
  if (!baseUrl) {
    throw new Error("worker was not initialized with a baseUrl");
  }
  const base = baseUrl;
  booting ??= createRuntime({
    indexURL: new URL("pyodide/", base).href,
    wheelName: WHEEL,
    async loadWheel() {
      return new Uint8Array(await (await fetchOrThrow(new URL(WHEEL, base))).arrayBuffer());
    },
    async loadBridge() {
      return bridgeSource;
    },
  }).then((r) => (runtime = r));
  return booting;
}

self.onmessage = async (event: MessageEvent) => {
  const { id, fn, argJson, base } = event.data ?? {};

  if (fn === "init") {
    baseUrl = base;
    (self as unknown as Worker).postMessage({ id, ok: true, result: "{}" });
    return;
  }

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
