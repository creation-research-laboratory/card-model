/**
 * The markers make a claim about the model — "the rate changes here" — so the
 * thing worth testing is that the claim is true, not that a line was drawn.
 *
 * Two of these check TypeScript against Python. `lambdaF2` reimplements a
 * read-only property of `GeneralModelParams`, and the DATE→AGE conversion
 * restates a relationship `chronology.py` owns. The precomputed file records
 * the package's own answer to both, so both can be checked rather than trusted.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { groupMarkers, lambdaF2, markersFor } from "./breakpoints.js";
import type { Calibration, GeneralParams } from "../model/types.js";

const WEB = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const data = JSON.parse(
  readFileSync(join(WEB, "public", "precomputed.json"), "utf8"),
);

interface RawChronology {
  age_of_earth: number;
  flood_start_date: number;
  flood_end_date: number;
  ice_age_end_date: number;
  flood_start_age: number;
  ice_age_end_age: number;
}

function calibrationFor(presetKey: string): Calibration {
  const preset = data.presets[presetKey];
  const chron: RawChronology = data.chronologies[preset.chronology];
  return {
    params: preset.params as GeneralParams,
    chronology: {
      ageOfEarth: chron.age_of_earth,
      floodStartDate: chron.flood_start_date,
      floodEndDate: chron.flood_end_date,
      iceAgeEndDate: chron.ice_age_end_date,
    },
  } as Calibration;
}

const PRESETS = Object.keys(data.presets) as string[];

describe("lambda_F2 agrees with the package", () => {
  for (const key of PRESETS) {
    it(`${key}: matches the value the generator emitted`, () => {
      const preset = data.presets[key];
      // Python computed `lambda_F2` from the property; this recomputes it in
      // JS. They must agree, or the "Flood ends" marker quotes a lambda the
      // model never had.
      const ours = lambdaF2(preset.params as GeneralParams);
      // Relative, and two-sided: `ratio - 1 < tol` alone would also accept a
      // value orders of magnitude too small.
      expect(Math.abs(ours / preset.lambda_F2 - 1)).toBeLessThan(1e-6);
      expect(ours).toBeGreaterThanOrEqual(preset.params.lambda_bg);
    });
  }
});

describe("what gets marked, and as what", () => {
  const markers = markersFor(calibrationFor("masoretic:kpg"));
  const byKey = Object.fromEntries(markers.map((m) => [m.key, m]));

  it("marks the two Flood breakpoints as rate changes", () => {
    expect(byKey.t_F.kind).toBe("rate");
    expect(byKey.t_F2.kind).toBe("rate");
  });

  it("marks the Ice Age as an anchor, because nothing changes there", () => {
    // `GeneralModel.breakpoints()` returns (t_c, t_F, t_F2). The end of the Ice
    // Age is not among them — it is the third constraint the curve was fitted
    // to. Drawing it as a rate change would assert something the model denies.
    expect(byKey.ice_age_end.kind).toBe("anchor");
    expect(byKey.ice_age_end.detail).toMatch(/not a rate change/i);
  });

  it("says what actually changes at the end of the Flood", () => {
    // lambda is continuous at t_F2; it is k that switches. A marker implying a
    // jump here would be wrong.
    expect(byKey.t_F2.detail).toMatch(/continuous/);
    expect(byKey.t_F2.detail).toMatch(/k_PF/);
    expect(byKey.t_F.detail).toMatch(/discontinuous/);
  });

  it("omits t_c when the Creation week is flat", () => {
    // The flood-only mode pins lambda_c to background and k_c to zero, so the
    // first two regions are both flat and t_c is a boundary where nothing
    // observable happens.
    const p = data.presets["masoretic:kpg"].params;
    expect(p.lambda_c).toBe(p.lambda_bg);
    expect(p.k_c).toBe(0);
    expect(byKey.t_c).toBeUndefined();
  });

  it("includes t_c once the Creation week is doing something", () => {
    const base = calibrationFor("masoretic:kpg");
    const active = {
      ...base,
      params: { ...base.params, lambda_c: 1e6, k_c: 1e-2 },
    } as Calibration;
    const keys = markersFor(active).map((m) => m.key);
    expect(keys).toContain("t_c");
  });
});

describe("DATE and AGE are not confused", () => {
  // The package's own trap: parameters are DATEs (years after Day 1) and the
  // axes are AGEs (years before present). The precomputed file records both,
  // so the conversion can be checked instead of assumed.
  for (const key of PRESETS) {
    it(`${key}: marker ages match the chronology's recorded ages`, () => {
      const preset = data.presets[key];
      const chron: RawChronology = data.chronologies[preset.chronology];
      const byKey = Object.fromEntries(
        markersFor(calibrationFor(key)).map((m) => [m.key, m]),
      );
      expect(byKey.t_F.trueAge).toBeCloseTo(chron.flood_start_age, 6);
      expect(byKey.ice_age_end.trueAge).toBeCloseTo(chron.ice_age_end_age, 6);
      // And the Flood ends one year *later*, so its AGE is one year smaller.
      expect(byKey.t_F.trueAge - byKey.t_F2.trueAge).toBeCloseTo(1, 6);
    });
  }
});

describe("grouping follows the pixel scale, not a hardcoded pair", () => {
  const markers = markersFor(calibrationFor("masoretic:kpg"));
  // The real axis: 596 px of plot across ~4500 years, reversed.
  const realistic = (age: number) => 596 - (age / 4500) * 596;

  it("collapses the Flood pair, which is 0.13 px wide", () => {
    const groups = groupMarkers(markers, realistic);
    const flood = groups.find((g) => g.markers.some((m) => m.key === "t_F"));
    expect(flood!.markers.map((m) => m.key).sort()).toEqual(["t_F", "t_F2"]);
  });

  it("keeps the Ice Age separate — it is 240 px away", () => {
    const groups = groupMarkers(markers, realistic);
    const ice = groups.find((g) => g.markers.some((m) => m.key === "ice_age_end"));
    expect(ice!.markers).toHaveLength(1);
  });

  it("separates the Flood pair once the axis can resolve a year", () => {
    // Proves the collapse is a consequence of scale rather than a rule about
    // these two names — a zoomed axis must show them apart.
    const zoomed = (age: number) => (4400 - age) * 50;
    const groups = groupMarkers(markers, zoomed);
    const keys = groups.map((g) => g.markers.map((m) => m.key));
    expect(keys).toContainEqual(["t_F"]);
    expect(keys).toContainEqual(["t_F2"]);
  });
});
