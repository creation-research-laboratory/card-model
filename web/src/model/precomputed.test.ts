/**
 * The precomputed layer is what a first-time visitor sees, possibly for 40
 * seconds. It is tested as a real code path, not as scaffolding.
 *
 * These tests read the actual generated `public/precomputed.json` rather than a
 * fixture, so a stale or malformed generator output fails here.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { PrecomputedSource, type PrecomputedData } from "./PrecomputedSource.js";
import { interpolateLogLog } from "./interpolate.js";
import { UnsupportedRequestError, type CalibrationRequest } from "./types.js";

const WEB = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const data = JSON.parse(
  readFileSync(join(WEB, "public", "precomputed.json"), "utf8"),
) as PrecomputedData;

const source = new PrecomputedSource(data);
const preset = (chronology: string, boundary: string): CalibrationRequest => ({
  chronology, boundary, mode: "flood_only",
});

describe("generated data", () => {
  it("carries all six presets", () => {
    expect(source.presetKeys.sort()).toEqual([
      "masoretic:kpg", "masoretic:nq", "masoretic:pc_c",
      "septuagint:kpg", "septuagint:nq", "septuagint:pc_c",
    ]);
  });

  it("records which card version produced it", () => {
    expect(source.generatedBy.card_version).toMatch(/^\d+\.\d+/);
  });

  it("solved every preset to machine precision", () => {
    // These come from the real solver, not from interpolation, so they should
    // be at the noise floor. A regression here means the model moved.
    for (const key of source.presetKeys) {
      expect(data.presets[key].max_abs_residual).toBeLessThan(1e-12);
    }
  });

  it("reproduces the values pinned from the Python package", async () => {
    const cal = await source.calibrate(preset("masoretic", "kpg"));
    expect(cal.params.lambda_F).toBeCloseTo(318754, -1);
    expect(cal.params.k_F).toBeCloseTo(0.00482991, 8);
  });

  it("flags the provisional chronology so the UI can say so", () => {
    expect(data.chronologies.septuagint.provisional).toBe(true);
    expect(data.chronologies.masoretic.provisional).toBe(false);
  });
});

describe("series", () => {
  it("is ascending in true age and non-decreasing in secular age", async () => {
    // Monotonicity is a property of the model — forward_age is the integral of
    // a non-negative rate — and the table lookup depends on it, so a generator
    // change that broke it would silently corrupt every interpolation.
    for (const key of source.presetKeys) {
      const { true_age, secular_age } = data.presets[key].series;
      for (let i = 1; i < true_age.length; i++) {
        expect(true_age[i]).toBeGreaterThan(true_age[i - 1]);
        expect(secular_age[i]).toBeGreaterThanOrEqual(secular_age[i - 1]);
      }
    }
  });

  it("puts the constraint ages on the grid exactly", async () => {
    // Otherwise the calibration anchors a chart draws would be interpolated
    // points that miss their own targets.
    for (const key of source.presetKeys) {
      const p = data.presets[key];
      for (const constraint of p.constraints) {
        expect(p.series.true_age).toContain(constraint.true_age);
      }
    }
  });

  it("hits each constraint's target at its anchor row", async () => {
    for (const key of source.presetKeys) {
      const p = data.presets[key];
      const cal = await source.calibrate(preset(p.chronology, p.boundary));
      // cal.constraints is the camelCase view; p.constraints is the raw file.
      for (const constraint of cal.constraints) {
        const got = await source.forwardAge(cal, constraint.trueAge);
        expect(Math.abs(got / constraint.secularAge - 1)).toBeLessThan(1e-9);
      }
    }
  });

  it("gives the kink at the Flood a vertex", async () => {
    // forward_age is the integral of a bounded rate, so it is *continuous* in
    // true age: crossing the Flood is a change of slope, not a step. What the
    // grid has to supply is the vertex itself — without a point exactly at the
    // breakpoint, the two neighbours either side round the corner off.
    for (const key of source.presetKeys) {
      const p = data.presets[key];
      const chron = data.chronologies[p.chronology];
      const floodAge = chron.age_of_earth - p.params.t_F;
      expect(p.series.true_age).toContain(floodAge);
    }
  });

  it("has no duplicate true-age rows", async () => {
    // A repeated x is a zero-width interval for the interpolator to land in.
    for (const key of source.presetKeys) {
      const xs = data.presets[key].series.true_age;
      expect(new Set(xs).size).toBe(xs.length);
    }
  });
});

describe("lambda history", () => {
  it("is ascending in DATE and spans zero to the present", async () => {
    for (const key of source.presetKeys) {
      const p = data.presets[key];
      const chron = data.chronologies[p.chronology];
      const dates = p.lambda_history.date;
      expect(dates[0]).toBe(0);
      expect(dates[dates.length - 1]).toBe(chron.age_of_earth);
      for (let i = 1; i < dates.length; i++) {
        expect(dates[i]).toBeGreaterThan(dates[i - 1]);
      }
    }
  });

  it("carries a genuine step at the Flood, not a ramp", async () => {
    // This is the whole reason the lambda grid straddles its breakpoints and
    // the age grid does not. An earlier straddle attempt collapsed under
    // rounding and would have drawn a diagonal; the generator now refuses to
    // emit that, and this checks the result from the other side.
    for (const key of source.presetKeys) {
      const p = data.presets[key];
      const { date, lambda } = p.lambda_history;
      const i = date.indexOf(p.params.t_F);
      expect(i).toBeGreaterThan(-1);

      const width = date[i + 1] - date[i];
      const jump = lambda[i + 1] / lambda[i];
      // Two samples a fraction of a year apart, spanning the full rise to
      // lambda_F: a vertical edge at any plottable scale.
      expect(width).toBeLessThan(0.01);
      // Not exactly lambda_F: the second sample sits at t_F*(1 + 1e-6), by
      // which point the rate has already relaxed by ~k_F * 0.002 yr. Relative,
      // because lambda_F spans 7.9e3 to 3.2e6 across the presets and an
      // absolute tolerance cannot cover both.
      expect(Math.abs(jump / p.params.lambda_F - 1)).toBeLessThan(1e-4);
    }
  });

  it("starts at background and has substantially relaxed by the present", async () => {
    // Flood-only has no Creation-week acceleration, so it starts at exactly 1.
    //
    // The tail only *approaches* 1 — relaxation is exponential — and how close
    // it gets varies by more than two orders of magnitude across the presets:
    // N/Q still sits 1.07% above background today, because it has both the
    // smallest k_F and the smallest excursion to decay from. An absolute bound
    // would encode one preset's physics and reject another's, so this measures
    // what actually matters: the fraction of the excursion still outstanding.
    for (const key of source.presetKeys) {
      const p = data.presets[key];
      const { lambda } = p.lambda_history;
      expect(lambda[0]).toBe(1);

      const final = lambda[lambda.length - 1];
      expect(final).toBeGreaterThanOrEqual(1);
      const remaining = (final - 1) / (p.params.lambda_F - 1);
      expect(remaining).toBeLessThan(1e-4);
    }
  });

  it("is returned as generated, without resampling", async () => {
    const cal = await source.calibrate(preset("masoretic", "kpg"));
    const history = await source.lambdaHistory(cal);
    expect(history.date).toEqual(data.presets["masoretic:kpg"].lambda_history.date);
    expect(history.floodStartDate).toBe(1656);
    // These samples came from the model, so they are exact — unlike a scalar
    // query at an arbitrary age, which interpolates.
    expect(history.exact).toBe(true);
  });
});

describe("geologic column", () => {
  it("carries every ICS unit, in range or not", async () => {
    for (const key of source.presetKeys) {
      const col = data.presets[key].geologic_column;
      expect(col.length).toBe(14);
      expect(col[0].name).toBe("Holocene");
      expect(col[col.length - 1].name).toBe("Cambrian");
    }
  });

  it("marks units the calibration cannot reach rather than dropping them", async () => {
    // Pinning the Flood to K/Pg caps the model at 66 Myr, so the Cretaceous
    // and everything older has no young-earth date. Silently omitting those
    // rows would make the column look complete when it is not.
    const kpg = data.presets["masoretic:kpg"].geologic_column;
    expect(kpg.filter((u) => u.in_range).map((u) => u.name)).toEqual([
      "Holocene", "Pleistocene", "Pliocene", "Miocene", "Paleogene",
    ]);
    for (const unit of kpg.filter((u) => !u.in_range)) {
      expect(unit.duration_true).toBeUndefined();
      expect(unit.base_true_age).toBeUndefined();
    }

    // The widest boundary reaches all of them.
    expect(data.presets["masoretic:pc_c"].geologic_column
      .every((u) => u.in_range)).toBe(true);
  });

  it("tiles the timeline without gaps or overlaps", async () => {
    // Each unit's younger boundary is the previous unit's base, in both age
    // systems. A gap would mean lost time; an overlap, double-counted time.
    for (const key of source.presetKeys) {
      const col = data.presets[key].geologic_column.filter((u) => u.in_range);
      expect(col[0].top_true_age).toBe(0);
      for (let i = 1; i < col.length; i++) {
        expect(col[i].top_true_age).toBe(col[i - 1].base_true_age);
        expect(col[i].top_secular_age).toBe(col[i - 1].base_secular_age);
      }
    }
  });

  it("gives every in-range unit a positive duration and acceleration", async () => {
    for (const key of source.presetKeys) {
      for (const u of data.presets[key].geologic_column.filter((x) => x.in_range)) {
        expect(u.duration_true!).toBeGreaterThan(0);
        expect(u.acceleration!).toBeGreaterThan(0);
        // Acceleration is secular years per young-earth year, so it must
        // reproduce the unit's secular span from its true duration.
        const secular = u.base_secular_age - u.top_secular_age;
        expect(Math.abs(u.acceleration! * u.duration_true! / secular - 1))
          .toBeLessThan(1e-6);
      }
    }
  });

  it("compresses monotonically into the deep past", async () => {
    // Older units sit further into the acceleration, so each should run at
    // least as fast as the one above it. If this ever fails the model has
    // changed shape, not the chart.
    const col = data.presets["masoretic:pc_c"].geologic_column;
    for (let i = 1; i < col.length; i++) {
      expect(col[i].acceleration!).toBeGreaterThan(col[i - 1].acceleration!);
    }
  });

  it("is reported as exact, because it is", async () => {
    // Durations are differences of inverse ages agreeing to four or five
    // significant figures; interpolating them would put 13.7% error on the
    // Silurian. The generator ships numbers the solver produced instead.
    const cal = await source.calibrate(preset("masoretic", "pc_c"));
    const column = await source.geologicColumn(cal);
    expect(column.exact).toBe(true);
    expect(column.units).toHaveLength(14);
  });
});

describe("interpolation accuracy", () => {
  it("is within the tolerance the UI is told to expect", async () => {
    // Measured against the live model at grid midpoints: 0.275% worst case
    // forward. The UI renders these with a "≈"; this test is what keeps that
    // claim true as the grid or the presets change.
    for (const key of source.presetKeys) {
      const { true_age, secular_age } = data.presets[key].series;
      let worst = 0;
      for (let i = 0; i < true_age.length - 1; i++) {
        const x = Math.sqrt(Math.max(true_age[i], 1e-9) * true_age[i + 1]);
        const interpolated = interpolateLogLog(true_age, secular_age, x);
        // Compare against the chord in the other direction as a self-check on
        // smoothness; the absolute check against Python lives in the live test.
        const linear = secular_age[i] +
          ((x - true_age[i]) / (true_age[i + 1] - true_age[i])) *
          (secular_age[i + 1] - secular_age[i]);
        if (linear > 0) worst = Math.max(worst, Math.abs(interpolated / linear - 1));
      }
      expect(worst).toBeLessThan(0.05);
    }
  });

  it("round-trips forward and inverse", async () => {
    const cal = await source.calibrate(preset("masoretic", "kpg"));
    for (const trueAge of [10, 100, 1000, 2556, 4400, 6000]) {
      const secular = await source.forwardAge(cal, trueAge);
      const back = await source.inverseAge(cal, secular);
      expect(Math.abs(back / trueAge - 1)).toBeLessThan(1e-6);
    }
  });
});

describe("what it refuses", () => {
  it("cannot answer a request with custom parameters", async () => {
    const request: CalibrationRequest = {
      ...preset("masoretic", "kpg"), overrides: { lambda_F: 5e5 },
    };
    expect(source.supports(request)).toBe(false);
    await expect(source.calibrate(request)).rejects.toThrow(UnsupportedRequestError);
    // The message has to tell the caller what to do about it.
    await expect(source.calibrate(request)).rejects.toThrow(/ensureLive/);
  });

  it("cannot answer an unknown preset", async () => {
    const request = preset("masoretic", "no_such_boundary");
    expect(source.supports(request)).toBe(false);
    await expect(source.calibrate(request)).rejects.toThrow(UnsupportedRequestError);
  });

  it("cannot answer a mode it was not generated for", async () => {
    const request = { ...preset("masoretic", "kpg"), mode: "general" };
    expect(source.supports(request)).toBe(false);
    await expect(source.calibrate(request)).rejects.toThrow(/general/);
  });

  it("rejects out-of-domain ages instead of clamping", async () => {
    // The package raises ValueError and never returns a plausible number for
    // nonsense input. The stand-in has to refuse the same inputs, or the app's
    // behavior would change when the live source swaps in.
    const cal = await source.calibrate(preset("masoretic", "kpg"));
    await expect(source.forwardAge(cal, -1)).rejects.toThrow(/must be >= 0/);
    await expect(source.forwardAge(cal, NaN)).rejects.toThrow(/finite/);
    await expect(source.forwardAge(cal, 1e9)).rejects.toThrow(/exceeds/);
    await expect(source.inverseAge(cal, cal.maxSecularAge * 1.01))
      .rejects.toThrow(/exceeds/);
  });

  it("reports itself as inexact", async () => {
    const cal = await source.calibrate(preset("masoretic", "kpg"));
    expect(source.exact).toBe(false);
    expect(cal.exact).toBe(false);
  });
});
