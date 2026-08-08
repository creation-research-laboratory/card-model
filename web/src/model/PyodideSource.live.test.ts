/**
 * The live source, against a real Pyodide interpreter, headlessly.
 *
 * This is the test that makes the whole architecture checkable without a
 * browser. It boots the same runtime the Worker boots, from the same vendored
 * files and the same wheel, and asks whether the answers match the Python
 * package — and whether the *precomputed* layer agrees with them closely enough
 * to stand in for it during the 12-42 s it takes Pyodide to arrive.
 *
 * Opt-in (`npm run test:live`), because booting costs ~1.5 s.
 */

import { readFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { PrecomputedSource, type PrecomputedData } from "./PrecomputedSource.js";
import { PyodideSource } from "./PyodideSource.js";
import { ModelError, type CalibrationRequest } from "./types.js";
import { DirectTransport } from "../worker/transport.js";

const WEB = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const WHEEL = "card_model-0.1.0-py3-none-any.whl";

const data = JSON.parse(
  readFileSync(join(WEB, "public", "precomputed.json"), "utf8"),
) as PrecomputedData;

const preset = (chronology: string, boundary: string): CalibrationRequest => ({
  chronology, boundary, mode: "flood_only",
});

let live: PyodideSource;
let precomputed: PrecomputedSource;

beforeAll(async () => {
  const transport = new DirectTransport({
    indexURL: join(WEB, "node_modules", "pyodide"),
    wheelName: WHEEL,
    loadWheel: async () => new Uint8Array(await readFile(join(WEB, "public", WHEEL))),
    loadBridge: () => readFile(join(WEB, "src", "worker", "bridge.py"), "utf8"),
  });
  live = new PyodideSource(transport, {
    chronologies: data.chronologies,
    boundaries: data.boundaries,
    secondConstraint: data.second_constraint,
  });
  precomputed = new PrecomputedSource(data);
  await live.boot();
});

afterAll(async () => {
  await live?.dispose();
});

describe("environment", () => {
  it("runs the card package with no numpy and no scipy", async () => {
    // The premise of shipping `card` to a browser. If this fails, the download
    // has quietly grown from 5.84 MB to ~22 MB.
    const env = await live.environment();
    expect(env.numpyLoaded).toBe(false);
    expect(env.scipyLoaded).toBe(false);
    expect(env.cardVersion).toMatch(/^\d+\.\d+/);
  });
});

describe("agreement with the Python package", () => {
  it("reproduces the pinned solve", async () => {
    const cal = await live.calibrate(preset("masoretic", "kpg"));
    expect(cal.params.lambda_F).toBeCloseTo(318753.882, 2);
    expect(cal.params.k_F).toBeCloseTo(0.00482991111, 10);
    expect(cal.maxAbsResidual).toBeLessThan(1e-12);
    expect(cal.exact).toBe(true);
  });

  it("solves every preset to machine precision", async () => {
    for (const key of precomputed.presetKeys) {
      const p = data.presets[key];
      const cal = await live.calibrate(preset(p.chronology, p.boundary));
      expect(cal.maxAbsResidual).toBeLessThan(1e-12);
      // And agrees with what the generator wrote into the static file.
      expect(cal.params.lambda_F / p.params.lambda_F - 1).toBeCloseTo(0, 8);
      expect(cal.params.k_F / p.params.k_F - 1).toBeCloseTo(0, 8);
    }
  });

  it("round-trips forward and inverse exactly", async () => {
    const cal = await live.calibrate(preset("masoretic", "kpg"));
    for (const trueAge of [1, 100, 2556, 4400, 6000]) {
      const secular = await live.forwardAge(cal, trueAge);
      const back = await live.inverseAge(cal, secular);
      expect(back).toBeCloseTo(trueAge, 6);
    }
  });
});

describe("the precomputed layer is a faithful stand-in", () => {
  it("matches the live model within the tolerance the UI advertises", async () => {
    // This is the number the "≈" in the UI is promising. Measured at grid
    // midpoints, where interpolation is worst.
    let worstForward = 0;
    let worstInverse = 0;

    for (const key of precomputed.presetKeys) {
      const p = data.presets[key];
      const request = preset(p.chronology, p.boundary);
      const liveCal = await live.calibrate(request);
      const preCal = await precomputed.calibrate(request);
      const xs = p.series.true_age;

      for (let i = 0; i < xs.length - 1; i += 7) {
        const x = Math.sqrt(Math.max(xs[i], 1e-9) * xs[i + 1]);
        if (!(x > 0 && x <= liveCal.chronology.ageOfEarth)) continue;

        const truth = await live.forwardAge(liveCal, x);
        if (truth <= 0) continue;
        const approx = await precomputed.forwardAge(preCal, x);
        worstForward = Math.max(worstForward, Math.abs(approx / truth - 1));

        const backApprox = await precomputed.inverseAge(preCal, truth);
        worstInverse = Math.max(worstInverse, Math.abs(backApprox / x - 1));
      }
    }

    expect(worstForward).toBeLessThan(5e-3);
    expect(worstInverse).toBeLessThan(1e-3);
  });

  it("agrees exactly on the solved parameters, which are not interpolated", async () => {
    // Only curve values are approximate. The generator ran the real solver for
    // the parameters and residuals, so those should match to the last digit
    // the file stores.
    for (const key of precomputed.presetKeys) {
      const p = data.presets[key];
      const request = preset(p.chronology, p.boundary);
      const liveCal = await live.calibrate(request);
      const preCal = await precomputed.calibrate(request);
      expect(preCal.params.lambda_F / liveCal.params.lambda_F - 1).toBeCloseTo(0, 8);
      expect(preCal.maxSecularAge / liveCal.maxSecularAge - 1).toBeCloseTo(0, 8);
    }
  });
});

describe("custom parameters — the thing only the live source can do", () => {
  it("accepts an override the precomputed layer must refuse", async () => {
    const request: CalibrationRequest = {
      ...preset("masoretic", "kpg"), overrides: { lambda_F: 5.0e5 },
    };
    expect(precomputed.supports(request)).toBe(false);

    const cal = await live.calibrate(request);
    expect(cal.params.lambda_F).toBeCloseTo(5.0e5, 6);
    // k_F still comes from the solve; only what was overridden changed.
    expect(cal.params.k_F).toBeCloseTo(0.00482991111, 10);
  });

  it("leaves the constraints undisturbed by Creation-week overrides", async () => {
    // Both constraint ages map to formation DATEs at or after t_F, so their
    // integrals never touch lambda_c or k_c. This is what makes the `general`
    // mode a data change rather than a new solver, so it is worth pinning.
    const base = await live.calibrate(preset("masoretic", "kpg"));
    const withCreation = await live.calibrate({
      ...preset("masoretic", "kpg"),
      overrides: { lambda_c: 1e8, k_c: 1e-3 },
    });

    for (const constraint of base.constraints) {
      const a = await live.forwardAge(base, constraint.trueAge);
      const b = await live.forwardAge(withCreation, constraint.trueAge);
      expect(b).toBe(a); // exactly, not approximately
    }

    // And it does change the pre-Flood part of the curve, or the override
    // would be doing nothing at all.
    const preFlood = base.chronology.ageOfEarth - 1;
    const before = await live.forwardAge(base, preFlood);
    const after = await live.forwardAge(withCreation, preFlood);
    expect(after).toBeGreaterThan(before * 10);
  });
});

describe("errors and warnings come from the package", () => {
  it("surfaces the package's own prose for an out-of-domain age", async () => {
    const cal = await live.calibrate(preset("masoretic", "kpg"));
    await expect(live.forwardAge(cal, -1)).rejects.toThrow(ModelError);
    // The package explains the AGE convention; that explanation should reach
    // the user rather than being replaced by something we made up.
    await expect(live.forwardAge(cal, -1)).rejects.toThrow(/years before present/);
    await expect(live.inverseAge(cal, 1e30)).rejects.toThrow(/exceeds the maximum/);
  });

  it("rejects a parameter the model considers invalid", async () => {
    await expect(live.calibrate({
      ...preset("masoretic", "kpg"), overrides: { lambda_F: 0.5 },
    })).rejects.toThrow(/must be >= 1/);
  });

  it("passes non-blocking warnings through instead of swallowing them", async () => {
    // A Flood longer than 2 years warns rather than raises. The browser should
    // not be quieter than the CLI about the same input.
    const cal = await live.calibrate({
      ...preset("masoretic", "kpg"), overrides: { t_F2: 1660 },
    });
    expect(cal.params.t_F2).toBe(1660);
    expect(live.lastWarnings.join(" ")).toMatch(/Flood duration/i);
  });
});

describe("the parameter schema comes from the package, not from TypeScript", () => {
  it("returns exactly the free names the flood-only mode leaves", async () => {
    // The payoff for running real `card`: add a parameter to the dataclass and
    // a control appears with no frontend change.
    const result = await live.schema("masoretic", {
      lambda_c: 1.0, k_c: 0.0, t_c: 1.0,
      t_F: "flood_start_date", t_F2: "flood_end_date",
    });
    expect(result.free.sort()).toEqual(["k_F", "lambda_F", "lambda_bg"].sort());
    // lambda_bg is present but not fittable (minimum == maximum), so a UI skips
    // it structurally rather than by a hardcoded exclusion.
    expect(result.fittable).not.toContain("lambda_bg");
    expect(result.fixed.t_F).toBe(1656);
  });

  it("resolves chronology names so a mode works across chronologies", async () => {
    const result = await live.schema("septuagint", {
      t_F: "flood_start_date", t_F2: "flood_end_date",
    });
    expect(result.fixed.t_F).toBe(2262);
  });

  it("gives date parameters bounds from the loaded chronology", async () => {
    // A DATE's upper bound is the age of the Earth, which is a chronology
    // setting rather than a constant.
    const result = await live.schema("septuagint", {});
    const properties = (result.schema as {
      properties: Record<string, { maximum: number }>;
    }).properties;
    expect(properties.t_F.maximum).toBe(7500);
  });

  it("would expose the Creation-week parameters if the general mode were on", async () => {
    // The expansion path, exercised. An unexercised path is a claim, not a
    // capability — so the `general` mode's fixed set is tested even though the
    // UI does not offer it in v1.
    const result = await live.schema("masoretic", {
      t_c: 1.0, t_F: "flood_start_date", t_F2: "flood_end_date",
    });
    expect(result.free).toContain("lambda_c");
    expect(result.free).toContain("k_c");
    expect(result.free).toContain("lambda_F");
    expect(result.free).toContain("k_F");
  });
});
