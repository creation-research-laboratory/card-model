/**
 * The lazy swap. This is the behavior the Phase 2 measurements bought, so it is
 * worth pinning: Pyodide must not start until something actually needs it.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";

import { ModelSourceManager } from "./ModelSourceManager.js";
import { PrecomputedSource, type PrecomputedData } from "./PrecomputedSource.js";
import type { PyodideSource } from "./PyodideSource.js";
import type { CalibrationRequest } from "./types.js";

const WEB = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const data = JSON.parse(
  readFileSync(join(WEB, "public", "precomputed.json"), "utf8"),
) as PrecomputedData;

const presetRequest: CalibrationRequest = {
  chronology: "masoretic", boundary: "kpg", mode: "flood_only",
};
const customRequest: CalibrationRequest = {
  ...presetRequest, overrides: { lambda_F: 5e5 },
};

/** Stand-in for PyodideSource; booting the real one takes ~1.5 s. */
function fakeLive(overrides: Partial<PyodideSource> = {}) {
  return {
    kind: "live" as const,
    exact: true,
    boot: vi.fn(async () => undefined),
    supports: () => true,
    dispose: vi.fn(async () => undefined),
    ...overrides,
  } as unknown as PyodideSource;
}

function makeManager(opts: {
  createLive?: () => Promise<PyodideSource>;
  idleBootDelayMs?: number | null;
} = {}) {
  const createLive = opts.createLive ?? vi.fn(async () => fakeLive());
  const manager = new ModelSourceManager({
    precomputed: new PrecomputedSource(data),
    createLive,
    idleBootDelayMs: opts.idleBootDelayMs ?? null,
  });
  return { manager, createLive };
}

describe("lazy boot", () => {
  it("does not start Pyodide on construction", () => {
    const { manager, createLive } = makeManager();
    expect(createLive).not.toHaveBeenCalled();
    expect(manager.state).toMatchObject({ kind: "precomputed", liveStatus: "idle" });
  });

  it("serves a preset without ever booting", async () => {
    const { manager, createLive } = makeManager();
    const source = await manager.resolve(presetRequest);
    const cal = await source.calibrate(presetRequest);

    expect(createLive).not.toHaveBeenCalled();
    expect(source.kind).toBe("precomputed");
    expect(cal.params.lambda_F / 3.21423e6 - 1).toBeCloseTo(0, 4);
  });

  it("boots when a request needs custom parameters", async () => {
    const { manager, createLive } = makeManager();
    expect(manager.needsLive(customRequest)).toBe(true);

    await manager.resolve(customRequest);
    expect(createLive).toHaveBeenCalledTimes(1);
    expect(manager.state).toMatchObject({ kind: "live", liveStatus: "ready" });
  });

  it("boots at most one interpreter under concurrent callers", async () => {
    // Two Pyodide instances is ~200 MB, and in the Phase 2 spike a reliable way
    // to make one of them stall. Every caller during boot must share one.
    let resolveBoot!: (s: PyodideSource) => void;
    const createLive = vi.fn(
      () => new Promise<PyodideSource>((r) => { resolveBoot = r; }),
    );
    const { manager } = makeManager({ createLive });

    const waiters = [manager.ensureLive(), manager.ensureLive(), manager.ensureLive()];
    expect(createLive).toHaveBeenCalledTimes(1);
    expect(manager.state.liveStatus).toBe("booting");

    resolveBoot(fakeLive());
    const settled = await Promise.all(waiters);
    expect(new Set(settled).size).toBe(1);
    expect(createLive).toHaveBeenCalledTimes(1);
  });

  it("is idempotent once ready", async () => {
    const { manager, createLive } = makeManager();
    const first = await manager.ensureLive();
    const second = await manager.ensureLive();
    expect(first).toBe(second);
    expect(createLive).toHaveBeenCalledTimes(1);
  });

  it("routes presets to the live source once it is up", async () => {
    // The precomputed layer is a stand-in until Pyodide arrives, not a
    // permanent fast path. Keeping it in service for presets afterwards would
    // trade exact answers for ~13 ms and make the UI inconsistent with itself:
    // the "≈" marker would flicker as the user moved between a preset and a
    // custom value. A stale comment on a since-deleted `sourceFor` claimed the
    // opposite policy, so this pins which one is real.
    const { manager } = makeManager();
    expect((await manager.resolve(presetRequest)).kind).toBe("precomputed");

    await manager.ensureLive();
    expect((await manager.resolve(presetRequest)).kind).toBe("live");
    expect(manager.current.kind).toBe("live");
  });
});

describe("failure handling", () => {
  it("reports the failure and stays usable on the precomputed source", async () => {
    const createLive = vi.fn(async () => { throw new Error("network died"); });
    const { manager } = makeManager({ createLive });

    await expect(manager.ensureLive()).rejects.toThrow("network died");
    expect(manager.state).toMatchObject({ kind: "precomputed", liveStatus: "failed" });
    expect(manager.state.error).toContain("network died");

    // The app is not dead: presets still work.
    const cal = await manager.current.calibrate(presetRequest);
    expect(cal.params.lambda_F / 3.21423e6 - 1).toBeCloseTo(0, 4);
  });

  it("allows a retry after a failed boot", async () => {
    // A boot failure is usually a dropped connection mid-download, not a
    // permanent condition, so the memo must not cache the rejection.
    let attempt = 0;
    const createLive = vi.fn(async () => {
      if (++attempt === 1) throw new Error("transient");
      return fakeLive();
    });
    const { manager } = makeManager({ createLive });

    await expect(manager.ensureLive()).rejects.toThrow("transient");
    await expect(manager.ensureLive()).resolves.toBeDefined();
    expect(createLive).toHaveBeenCalledTimes(2);
    expect(manager.state.liveStatus).toBe("ready");
  });
});

describe("notifications", () => {
  it("tells subscribers when the source changes", async () => {
    const { manager } = makeManager();
    const seen: string[] = [];
    manager.subscribe((s) => seen.push(`${s.kind}/${s.liveStatus}`));

    await manager.ensureLive();
    expect(seen).toEqual(["precomputed/booting", "live/ready"]);
  });

  it("stops notifying after unsubscribe", async () => {
    const { manager } = makeManager();
    const seen: string[] = [];
    const off = manager.subscribe((s) => seen.push(s.liveStatus));
    off();
    await manager.ensureLive();
    expect(seen).toEqual([]);
  });
});

describe("idle boot", () => {
  it("is off unless asked for", async () => {
    vi.useFakeTimers();
    try {
      const { createLive } = makeManager({ idleBootDelayMs: null });
      await vi.advanceTimersByTimeAsync(60_000);
      expect(createLive).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("boots after the configured delay when enabled", async () => {
    vi.useFakeTimers();
    try {
      const { manager, createLive } = makeManager({ idleBootDelayMs: 5_000 });
      await vi.advanceTimersByTimeAsync(4_000);
      expect(createLive).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(2_000);
      expect(createLive).toHaveBeenCalledTimes(1);
      await manager.ensureLive();
      expect(manager.state.liveStatus).toBe("ready");
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not double-boot when interaction beats the timer", async () => {
    vi.useFakeTimers();
    try {
      const { manager, createLive } = makeManager({ idleBootDelayMs: 5_000 });
      await manager.ensureLive();
      await vi.advanceTimersByTimeAsync(10_000);
      expect(createLive).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
