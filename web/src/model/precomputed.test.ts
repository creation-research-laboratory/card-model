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
  it("carries all four presets", () => {
    // Two chronologies x two post-Flood boundaries. The Flood's *start* is not
    // a variable — it is always the pre-Flood contact.
    expect(source.presetKeys.sort()).toEqual([
      "masoretic:kpg", "masoretic:nq", "septuagint:kpg", "septuagint:nq",
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
    expect(cal.params.lambda_F / 4.54657e9 - 1).toBeCloseTo(0, 4);
    // k_F relaxes *during* the Flood; k_PF after it. Both are pinned, because
    // the whole point of the three-pair solve is that they differ by three
    // orders of magnitude, and swapping them would look plausible.
    expect(cal.params.k_F).toBeCloseTo(9.571, 2);
    expect(cal.params.k_PF).toBeCloseTo(0.00480302, 7);
  });

  it("gives the Flood a real length, because lambda relaxes across it", async () => {
    // t_F2 > t_F now. When one k had to serve both phases the onset was
    // instantaneous and the Flood year was only a constraint age; k_F makes it
    // a model interval with its own relaxation.
    const cal = await source.calibrate(preset("masoretic", "kpg"));
    expect(cal.params.t_F2).toBeGreaterThan(cal.params.t_F);
    expect(cal.params.t_F2 - cal.params.t_F).toBeCloseTo(1, 9);
  });

  it("calibrates on three pairs", async () => {
    for (const key of source.presetKeys) {
      const p = data.presets[key];
      expect(p.constraints).toHaveLength(3);
      expect(p.residuals).toHaveLength(3);
      const [onset, cease, ice] = p.constraints;
      expect(onset.secular_age).toBe(541e6);
      expect(cease.secular_age).toBe(data.boundaries[p.boundary].secular_age);
      expect(ice.secular_age).toBe(12000);
      // The first two are the Flood year's ends; the third is millennia later.
      expect(onset.true_age - cease.true_age).toBeCloseTo(1, 9);
      expect(cease.true_age).toBeGreaterThan(ice.true_age);
    }
  });

  it("separates the in-Flood and post-Flood rates by orders of magnitude", async () => {
    // This is what the third pair buys, and the reason one k could not do the
    // job: the Flood year needs k ~ 10/yr while the millennia after it need
    // ~0.005/yr. If these ever converge, the model has collapsed back.
    for (const key of source.presetKeys) {
      const { k_F, k_PF } = data.presets[key].params;
      expect(k_F).toBeGreaterThan(1);
      expect(k_PF).toBeLessThan(0.05);
      expect(k_F / k_PF).toBeGreaterThan(100);
    }
  });

  it("hands over continuously at the Flood's end", async () => {
    // lambda_F2 is not free: it is what the in-Flood exponential has fallen to
    // by t_F2, and the amplitude the post-Flood one starts from. That
    // continuity is what makes k_F one new degree of freedom, not two.
    for (const key of source.presetKeys) {
      const p = data.presets[key];
      const { lambda_F, k_F, t_F, t_F2 } = p.params;
      const expected = (lambda_F - 1) * Math.exp(-k_F * (t_F2 - t_F)) + 1;
      expect(Math.abs(p.lambda_F2 / expected - 1)).toBeLessThan(1e-6);
      // And it is a long way down from the peak — most of the drop is inside
      // the Flood year.
      expect(lambda_F / p.lambda_F2).toBeGreaterThan(100);
    }
  });

  it("gives each post-Flood boundary its own calibration", async () => {
    // The boundary is an input, so K/Pg and N/Q must not share a curve.
    for (const chron of ["masoretic", "septuagint"]) {
      const a = data.presets[`${chron}:kpg`].params;
      const b = data.presets[`${chron}:nq`].params;
      expect(a.lambda_F).not.toBe(b.lambda_F);
      // N/Q compresses more of the column into the Flood, so it needs a
      // fiercer in-Flood relaxation.
      expect(b.k_F).toBeGreaterThan(a.k_F);
    }
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
      // Both breakpoints now: the onset and the Flood's end.
      for (const date of [p.params.t_F, p.params.t_F2]) {
        expect(p.series.true_age).toContain(chron.age_of_earth - date);
      }
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
      // Not exactly lambda_F: the sample sits just past t_F, by which point
      // the rate has already relaxed. Checked against the decay the model
      // actually predicts over that gap rather than a hand-picked tolerance,
      // so this stays correct whatever k_F the calibration lands on.
      const gap = date[i + 1] - p.params.t_F;
      const expected = Math.exp(-p.params.k_F * gap);
      expect(jump / p.params.lambda_F).toBeCloseTo(expected, 6);
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
    // Defensive rather than exercised by the presets: now that the Flood
    // begins at the Precambrian-Cambrian boundary, the ceiling is 540 Ma for
    // every preset and the whole column is reachable. A custom parameter set
    // can still fall short, and an omitted row would make the column look
    // complete when it is not.
    for (const key of source.presetKeys) {
      for (const unit of data.presets[key].geologic_column.filter((u) => !u.in_range)) {
        expect(unit.duration_true).toBeUndefined();
        expect(unit.base_true_age).toBeUndefined();
      }
    }

    // And with the Flood starting at the Precambrian-Cambrian boundary, every
    // preset now reaches the whole column — the ceiling is 540 Ma regardless
    // of where the Flood ends.
    for (const key of source.presetKeys) {
      expect(data.presets[key].geologic_column.every((u) => u.in_range)).toBe(true);
    }
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
    // lambda is still falling throughout the Flood's depositional year, so
    // every unit runs strictly faster than the one above it — right down to
    // the Cambrian. A plateau here would mean the acceleration had been
    // modelled as constant across the Flood, which is a different model.
    for (const key of source.presetKeys) {
      const col = data.presets[key].geologic_column;
      for (let i = 1; i < col.length; i++) {
        expect(col[i].acceleration!).toBeGreaterThan(col[i - 1].acceleration!);
      }
    }
  });

  it("is reported as exact, because it is", async () => {
    // Durations are differences of inverse ages agreeing to four or five
    // significant figures; interpolating them would put 13.7% error on the
    // Silurian. The generator ships numbers the solver produced instead.
    const cal = await source.calibrate(preset("masoretic", "kpg"));
    const column = await source.geologicColumn(cal);
    expect(column.exact).toBe(true);
    expect(column.units).toHaveLength(14);
  });
});

describe("interpolation accuracy", () => {
  it("reproduces the table exactly at its own nodes", async () => {
    // Interpolation must be an identity on the grid points themselves. The
    // real accuracy question — how wrong it is *between* nodes — is answered
    // against the live model in the live suite, which is the only place it can
    // honestly be measured.
    for (const key of source.presetKeys) {
      const { true_age, secular_age } = data.presets[key].series;
      for (let i = 0; i < true_age.length; i += 37) {
        if (true_age[i] <= 0) continue;
        // Relative: these span 1 to 5.4e8, and an absolute tolerance that
        // suits one end is meaningless at the other. The log-log round trip
        // costs an ulp or two, which is the floor here.
        const got = interpolateLogLog(true_age, secular_age, true_age[i]);
        expect(Math.abs(got / secular_age[i] - 1)).toBeLessThan(1e-12);
      }
    }
  });

  it("round-trips forward and inverse", async () => {
    const cal = await source.calibrate(preset("masoretic", "kpg"));
    for (const trueAge of [10, 100, 1000, 2556, 4400, 6000]) {
      const secular = await source.forwardAge(cal, trueAge);
      const back = await source.inverseAge(cal, secular);
      // 2%: a round trip compounds both directions, and the inverse alone is
      // good to ~1% on this curve. The live suite measures each direction
      // against the model; this only checks they are consistent with each
      // other.
      expect(Math.abs(back / trueAge - 1)).toBeLessThan(2e-2);
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
