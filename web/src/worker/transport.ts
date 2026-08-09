/**
 * How `PyodideSource` reaches `bridge.py`.
 *
 * Two transports, one interface. `WorkerTransport` is what ships: Pyodide lives
 * in a Web Worker, because a multi-second boot on the main thread means a
 * frozen page and per-keystroke recalculation would jank a dragged slider.
 * `DirectTransport` runs the same runtime in-process, which is how the test
 * suite exercises the live path without a browser.
 */

import { createRuntime, type PyodideRuntime, type RuntimeResources } from "./pyodideRuntime.js";

export interface BridgeTransport {
  call(fn: string, argJson?: string): Promise<string>;
  dispose(): Promise<void>;
}

/** In-process. Used by tests, and usable from Node generally. */
export class DirectTransport implements BridgeTransport {
  private runtime: PyodideRuntime | null = null;
  private booting: Promise<PyodideRuntime> | null = null;

  constructor(private readonly resources: RuntimeResources) {}

  private async ready(): Promise<PyodideRuntime> {
    if (this.runtime) return this.runtime;
    // Guard against a second caller starting a second interpreter while the
    // first is still booting — two Pyodide instances is ~200 MB and, in the
    // Phase 2 spike, a reliable way to make one of them stall.
    this.booting ??= createRuntime(this.resources).then((r) => (this.runtime = r));
    return this.booting;
  }

  async call(fn: string, argJson?: string): Promise<string> {
    return (await this.ready()).call(fn, argJson);
  }

  async dispose(): Promise<void> {
    this.runtime?.destroy();
    this.runtime = null;
    this.booting = null;
  }
}

interface PendingCall {
  resolve(value: string): void;
  reject(error: Error): void;
}

/** Across a Web Worker boundary. What the browser uses. */
export class WorkerTransport implements BridgeTransport {
  private nextId = 0;
  private readonly pending = new Map<number, PendingCall>();
  private disposed = false;

  /**
   * @param worker  The Pyodide worker.
   * @param baseUrl Absolute URL of the directory holding `pyodide/`, the card
   *   wheel and `bridge.py`. Required because the worker does not live where
   *   its assets do — in dev it is served from /src/worker/, in production it
   *   is a hashed bundle, and the app deploys under a subpath.
   */
  constructor(private readonly worker: Worker, baseUrl: string) {
    worker.onmessage = (event: MessageEvent) => {
      const { id, ok, result, error } = event.data ?? {};
      const entry = this.pending.get(id);
      if (!entry) return;
      this.pending.delete(id);
      if (ok) entry.resolve(result as string);
      else entry.reject(new Error(String(error)));
    };

    // Without this, a failure while the worker's own module graph loads is
    // completely silent: onmessage never fires and every caller hangs forever.
    // The Phase 2 spike sat on "booting…" for exactly this reason.
    worker.onerror = (event: ErrorEvent) => {
      const message =
        `worker failed to load: ${event.message || "(no message)"} ` +
        `@ ${event.filename || "?"}:${event.lineno ?? "?"}`;
      this.failAll(new Error(message));
    };

    // Sent before anything else so the worker knows where its assets live.
    // Fire-and-forget: any later call queues behind it in the message order.
    worker.postMessage({ id: this.nextId++, fn: "init", base: baseUrl });
  }

  private failAll(error: Error): void {
    for (const entry of this.pending.values()) entry.reject(error);
    this.pending.clear();
  }

  call(fn: string, argJson?: string): Promise<string> {
    if (this.disposed) {
      return Promise.reject(new Error("transport disposed"));
    }
    const id = this.nextId++;
    return new Promise<string>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ id, fn, argJson });
    });
  }

  async dispose(): Promise<void> {
    this.disposed = true;
    this.failAll(new Error("transport disposed"));
    this.worker.terminate();
  }
}
