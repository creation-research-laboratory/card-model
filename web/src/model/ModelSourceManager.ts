/**
 * Owns which source is answering, and when the live one starts.
 *
 * The loading strategy here is the direct consequence of the Phase 2
 * measurements, and it is the opposite of what the plan originally specified.
 * Payload is a fixed 5.84 MB and boot is essentially all download: 42 s at a
 * measured 142 kB/s, ~12 s at 4 Mbps, ~3 s at 25 Mbps. Booting eagerly on page
 * load would hold a first-time visitor at a spinner for that long.
 *
 * So Pyodide does **not** start on load. It starts when the user does something
 * that needs it — touching a parameter control — or, optionally, once the page
 * has been visible and idle for a moment. Someone who only wants to look at the
 * presets never pays the cost; someone reaching for a slider has already asked
 * for the live model and will tolerate a wait they understand.
 */

import type { ModelSource, SourceKind } from "./ModelSource.js";
import type { PrecomputedSource } from "./PrecomputedSource.js";
import type { PyodideSource } from "./PyodideSource.js";
import { type CalibrationRequest, hasOverrides } from "./types.js";

export type LiveStatus = "idle" | "booting" | "ready" | "failed";

export interface ManagerState {
  kind: SourceKind;
  liveStatus: LiveStatus;
  error?: string;
}

export interface ModelSourceManagerOptions {
  precomputed: PrecomputedSource;
  /**
   * Deferred so that merely constructing the manager does not import the
   * Pyodide module graph — which is most of the point.
   */
  createLive: () => Promise<PyodideSource>;
  /**
   * Start the interpreter after this many ms of the page being visible, even
   * with no interaction. `null` disables it, which is the right choice on a
   * connection where the download would compete with anything else. Default is
   * null: explicit intent only.
   */
  idleBootDelayMs?: number | null;
  /** Injectable for tests. */
  now?: () => number;
}

export class ModelSourceManager {
  private readonly precomputed: PrecomputedSource;
  private readonly createLive: () => Promise<PyodideSource>;
  private live: PyodideSource | null = null;
  private livePromise: Promise<PyodideSource> | null = null;
  private status: LiveStatus = "idle";
  private lastError: string | undefined;
  private readonly listeners = new Set<(state: ManagerState) => void>();
  private idleTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private readonly options: ModelSourceManagerOptions) {
    this.precomputed = options.precomputed;
    this.createLive = options.createLive;
    if (options.idleBootDelayMs != null) {
      this.idleTimer = setTimeout(() => {
        // Failure of a speculative boot must not surface as an unhandled
        // rejection; the user never asked for it.
        void this.ensureLive().catch(() => undefined);
      }, options.idleBootDelayMs);
    }
  }

  /** The source to use right now. Never null; falls back to precomputed. */
  get current(): ModelSource {
    return this.live ?? this.precomputed;
  }

  get state(): ManagerState {
    return {
      kind: this.live ? "live" : "precomputed",
      liveStatus: this.status,
      error: this.lastError,
    };
  }

  /** True when this request needs the live source that is not up yet. */
  needsLive(request: CalibrationRequest): boolean {
    return !this.live && !this.precomputed.supports(request);
  }

  /**
   * Start the live source if it is not started, and resolve when it is ready.
   *
   * Idempotent and concurrency-safe: many callers during boot share one
   * interpreter. Two Pyodide instances is ~200 MB and, in the Phase 2 spike,
   * a reliable way to make one of them stall.
   */
  async ensureLive(): Promise<PyodideSource> {
    if (this.live) return this.live;
    if (this.livePromise) return this.livePromise;

    this.cancelIdleBoot();
    this.status = "booting";
    this.lastError = undefined;
    this.emit();

    this.livePromise = (async () => {
      try {
        const source = await this.createLive();
        await source.boot();
        this.live = source;
        this.status = "ready";
        this.emit();
        return source;
      } catch (error) {
        this.status = "failed";
        this.lastError = error instanceof Error ? error.message : String(error);
        // Clear the memo so a retry is possible — a boot failure is often
        // transient (a dropped connection mid-download).
        this.livePromise = null;
        this.emit();
        throw error;
      }
    })();

    return this.livePromise;
  }

  /**
   * Get whatever can answer this, booting the live source only if the request
   * actually requires it. The single entry point the UI should use.
   *
   * **Once the live source is up, everything routes to it — presets included.**
   * The precomputed layer is a stand-in until Pyodide arrives, not a permanent
   * fast path for presets. Keeping it in service afterwards would trade exact
   * answers for ~13 ms, and worse, would make the UI inconsistent with itself:
   * the "≈" marker would flicker on and off as the user switched between a
   * preset and a custom value, and displayed digits would shift for no reason
   * visible to them.
   */
  async resolve(request: CalibrationRequest): Promise<ModelSource> {
    if (this.live) return this.live;
    if (!hasOverrides(request) && this.precomputed.supports(request)) {
      return this.precomputed;
    }
    return this.ensureLive();
  }

  subscribe(listener: (state: ManagerState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async dispose(): Promise<void> {
    this.cancelIdleBoot();
    await this.live?.dispose();
    this.live = null;
    this.livePromise = null;
    this.status = "idle";
    this.listeners.clear();
  }

  private cancelIdleBoot(): void {
    if (this.idleTimer !== null) {
      clearTimeout(this.idleTimer);
      this.idleTimer = null;
    }
  }

  private emit(): void {
    const state = this.state;
    for (const listener of this.listeners) listener(state);
  }
}
