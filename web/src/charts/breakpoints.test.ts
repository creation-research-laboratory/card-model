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

import {
  DAYS_PER_YEAR, abbreviate, groupMarkers, lambdaF2, markersFor,
} from "./breakpoints.js";
import type { Calibration, GeneralParams } from "../model/types.js";
import { bodyOf } from "../model/testData.js";

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

/** The Ice Age DATE this preset was actually solved at. */
function iceAgeDateFor(preset: { chronology: string; ice_age: string }): number {
  const chron: RawChronology = data.chronologies[preset.chronology];
  const offset =
    data.ice_age_offsets.options[preset.ice_age].years_after_flood[preset.chronology];
  return chron.flood_end_date + offset;
}

function calibrationFor(presetKey: string): Calibration {
  const preset = data.presets[presetKey];
  const chron: RawChronology = data.chronologies[preset.chronology];
  return {
    params: preset.params as GeneralParams,
    constraints: preset.constraints.map((c: {
      label: string; true_age: number; secular_age: number; uncertainty: number;
    }) => ({
      label: c.label, trueAge: c.true_age,
      secularAge: c.secular_age, uncertainty: c.uncertainty,
    })),
    chronology: {
      ageOfEarth: chron.age_of_earth,
      floodStartDate: chron.flood_start_date,
      floodEndDate: chron.flood_end_date,
      // The preset's own, not the catalogue's: the Ice Age offset is a
      // separate dimension now, so `chronologies[...].ice_age_end_date` is
      // only right for the `default` offset.
      iceAgeEndDate: iceAgeDateFor(preset),
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

/** The one marker that is a fitted date rather than a breakpoint. */
const anchor = (ms: ReturnType<typeof markersFor>) =>
  ms.find((m) => m.kind === "anchor")!;

describe("what gets marked, and as what", () => {
  const markers = markersFor(calibrationFor("masoretic:kpg:default"));
  const byKey = Object.fromEntries(markers.map((m) => [m.key, m]));

  it("marks the two Flood breakpoints as rate changes", () => {
    expect(byKey.t_F.kind).toBe("rate");
    expect(byKey.t_F2.kind).toBe("rate");
  });

  it("marks the Ice Age as an anchor, because nothing changes there", () => {
    // `GeneralModel.breakpoints()` returns (t_c, t_F, t_F2). The end of the Ice
    // Age is not among them — it is the third constraint the curve was fitted
    // to. Drawing it as a rate change would assert something the model denies.
    expect(anchor(markers).kind).toBe("anchor");
    expect(anchor(markers).detail).toMatch(/not a rate change/i);
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
    const p = data.presets["masoretic:kpg:default"].params;
    expect(p.lambda_c).toBe(p.lambda_bg);
    expect(p.k_c).toBe(0);
    expect(byKey.t_c).toBeUndefined();
  });

  it("includes t_c once the Creation week is doing something", () => {
    const base = calibrationFor("masoretic:kpg:default");
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
      const ice = Object.values(byKey).find((m) => m.kind === "anchor")!;
      expect(ice.trueAge)
        .toBeCloseTo(chron.age_of_earth - iceAgeDateFor(preset), 6);
      // And the Flood ends one year *later*, so its AGE is one year smaller.
      expect(byKey.t_F.trueAge - byKey.t_F2.trueAge).toBeCloseTo(1, 6);
    });
  }
});

describe("grouping follows the pixel scale, not a hardcoded pair", () => {
  // The full view draws breakpoints and anchors only — the Flood-day marks are
  // filtered out there, because the year holding them is 0.13 px wide — so the
  // grouping these assertions describe is the grouping of those.
  const markers = markersFor(calibrationFor("masoretic:kpg:default"))
    .filter((m) => m.kind !== "reference");
  // The real axis: 596 px of plot across ~4500 years, reversed.
  const realistic = (age: number) => 596 - (age / 4500) * 596;

  it("collapses the Flood pair, which is 0.13 px wide", () => {
    const groups = groupMarkers(markers, realistic);
    const flood = groups.find((g) => g.markers.some((m) => m.key === "t_F"));
    expect(flood!.markers.map((m) => m.key).sort()).toEqual(["t_F", "t_F2"]);
  });

  it("keeps the Ice Age separate — it is 240 px away", () => {
    const groups = groupMarkers(markers, realistic);
    const ice = groups.find((g) => g.markers.some((m) => m.kind === "anchor"));
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

describe("the Flood/post-Flood breakpoint names the boundary that was chosen", () => {
  // The reason this module reads constraint labels instead of writing its own.
  // `t_F2` *is* the contact the reader selected in the preset picker, so the
  // point where the exponential hands over from k_F to k_PF has to say K/Pg or
  // N/Q. A marker reading only "Flood ends" hid that.
  it("says K/Pg when the K/Pg boundary is selected", () => {
    const byKey = Object.fromEntries(
      markersFor(calibrationFor("masoretic:kpg:default")).map((m) => [m.key, m]),
    );
    expect(byKey.t_F2.boundary).toBe("Cretaceous-Paleogene (K/Pg)");
    expect(byKey.t_F2.detail).toContain("Cretaceous-Paleogene (K/Pg)");
  });

  it("says N/Q when the N/Q boundary is selected", () => {
    const byKey = Object.fromEntries(
      markersFor(calibrationFor("masoretic:nq:default")).map((m) => [m.key, m]),
    );
    expect(byKey.t_F2.boundary).toBe("Neogene-Quaternary (N/Q)");
  });

  it("names the Flood onset as the Precambrian-Cambrian contact", () => {
    const byKey = Object.fromEntries(
      markersFor(calibrationFor("masoretic:kpg:default")).map((m) => [m.key, m]),
    );
    expect(byKey.t_F.boundary).toBe("Precambrian-Cambrian");
  });

  it("abbreviates for the figure but keeps the full name for the text", () => {
    expect(abbreviate("Cretaceous-Paleogene (K/Pg)")).toBe("K/Pg");
    expect(abbreviate("Neogene-Quaternary (N/Q)")).toBe("N/Q");
    // No parenthetical, so nothing to shorten — better than inventing one.
    expect(abbreviate("Precambrian-Cambrian")).toBe("Precambrian-Cambrian");
  });

  it("drops the contact name if a breakpoint is moved off it", () => {
    // Overriding t_F moves the Flood away from the Precambrian-Cambrian
    // contact, and the marker must stop claiming to sit on it.
    const base = calibrationFor("masoretic:kpg:default");
    const moved = {
      ...base, params: { ...base.params, t_F: base.params.t_F - 300 },
    } as Calibration;
    const byKey = Object.fromEntries(markersFor(moved).map((m) => [m.key, m]));
    expect(byKey.t_F.boundary).toBeUndefined();
    expect(byKey.t_F.label).toBe("Flood begins");
  });

  it("marks the boundary at the same true age the column puts it", () => {
    // The whole claim: the exponential changes exactly where the chosen
    // contact sits. For K/Pg that is the base of the Paleogene.
    // Every boundary, now that the Paleogene is split into its epochs and each
    // one has a contact the column draws.
    for (const [preset, unit] of [
      ["masoretic:pt:default", "Triassic"],
      ["masoretic:kpg:default", "Paleocene"],
      ["masoretic:pe:default", "Eocene"],
      ["masoretic:eo:default", "Oligocene"],
      ["masoretic:om:default", "Miocene"],
      ["masoretic:mp:default", "Pliocene"],
      ["masoretic:nq:default", "Pleistocene"],
    ] as const) {
      const byKey = Object.fromEntries(
        markersFor(calibrationFor(preset)).map((m) => [m.key, m]),
      );
      // The column lives in the preset's own file now, not the index.
      const base = bodyOf(preset).geologic_column
        .find((u) => u.name === unit)!.base_true_age!;
      expect(byKey.t_F2.trueAge).toBeCloseTo(base, 6);
    }
  });
});

describe("a contact is claimed only while the model still puts it there", () => {
  // The constraint's trueAge is a *target* and never moves, so matching on it
  // alone claimed K/Pg forever. Raising lambda_F walks the real contact
  // hundreds of years off t_F2 while the constraint stays at 4399.
  const solved = calibrationFor("masoretic:kpg:default");

  it("names the contact while the fit holds", () => {
    const byKey = Object.fromEntries(markersFor(solved).map((m) => [m.key, m]));
    expect(byKey.t_F2.boundary).toBe("Cretaceous-Paleogene (K/Pg)");
    expect(byKey.t_F2.displaced).toBeUndefined();
  });

  it("stops claiming it once a slider breaks the fit", () => {
    const broken = {
      ...solved,
      // What a slider does: parameters change, targets do not.
      params: { ...solved.params, lambda_F: solved.params.lambda_F * 3 },
      residuals: [0, 0.42, 0],
    } as Calibration;
    const byKey = Object.fromEntries(markersFor(broken).map((m) => [m.key, m]));
    expect(byKey.t_F2.boundary).toBeUndefined();
    expect(byKey.t_F2.displaced).toBe("Cretaceous-Paleogene (K/Pg)");
    expect(byKey.t_F2.detail).toMatch(/no longer falls here/);
    // The other two are untouched, so they keep their names.
    expect(byKey.t_F.boundary).toBe("Precambrian-Cambrian");
  });

  it("tolerates arithmetic noise but not a real move", () => {
    const noisy = { ...solved, residuals: [0, 1e-13, 0] } as Calibration;
    const nudged = { ...solved, residuals: [0, 1e-3, 0] } as Calibration;
    const boundaryOf = (c: Calibration) =>
      markersFor(c).find((m) => m.key === "t_F2")!.boundary;
    expect(boundaryOf(noisy)).toBe("Cretaceous-Paleogene (K/Pg)");
    expect(boundaryOf(nudged)).toBeUndefined();
  });

  it("recomputes lambda_F2 from the parameters in hand", () => {
    // The readout used to read this from the preset table, so it kept
    // reporting the value the preset was solved with after an override.
    const moved = {
      ...solved, params: { ...solved.params, k_F: solved.params.k_F / 2 },
    } as Calibration;
    expect(lambdaF2(moved.params)).not.toBeCloseTo(lambdaF2(solved.params), 0);
    // Relaxing more slowly leaves lambda higher at the Flood's end.
    expect(lambdaF2(moved.params)).toBeGreaterThan(lambdaF2(solved.params));
  });
});

describe("the Flood-day reference marks", () => {
  const solved = calibrationFor("masoretic:kpg:default");
  const byKey = Object.fromEntries(markersFor(solved).map((m) => [m.key, m]));

  it("places them by day count, not by eye", () => {
    const floodStart = solved.chronology.ageOfEarth - solved.params.t_F;
    expect(byKey["day:40"].trueAge).toBeCloseTo(floodStart - 40 / DAYS_PER_YEAR, 9);
    expect(byKey["day:150"].trueAge).toBeCloseTo(floodStart - 150 / DAYS_PER_YEAR, 9);
  });

  it("uses the same year length as the bar durations", () => {
    // `formatDuration` renders sub-year spans in days at 365.25. A different
    // constant here would put a bar labelled "69 days" on the wrong side of
    // the 40-day mark.
    expect(DAYS_PER_YEAR).toBe(365.25);
  });

  it("keeps them inside the Flood year", () => {
    const floodStart = solved.chronology.ageOfEarth - solved.params.t_F;
    const floodEnd = solved.chronology.ageOfEarth - solved.params.t_F2;
    for (const key of ["day:40", "day:150"]) {
      expect(byKey[key].trueAge).toBeLessThan(floodStart);
      expect(byKey[key].trueAge).toBeGreaterThan(floodEnd);
    }
  });

  it("is neither a breakpoint nor an anchor, and says so", () => {
    // The distinction the whole marker layer is built on. lambda is smooth
    // across both of these and nothing was fitted to them, so a reader must
    // not be able to mistake them for either.
    for (const key of ["day:40", "day:150"]) {
      expect(byKey[key].kind).toBe("reference");
      expect(byKey[key].detail).toMatch(/model has no feature here/);
      expect(byKey[key].boundary).toBeUndefined();
    }
  });

  it("drops a day the Flood never reached", () => {
    // t_F2 is settable. In the instantaneous-Flood limit the Flood has no
    // days, so marking "150 days" would place it outside the Flood entirely.
    const instant = {
      ...solved, params: { ...solved.params, t_F2: solved.params.t_F },
    } as Calibration;
    const keys = markersFor(instant).map((m) => m.key);
    expect(keys).not.toContain("day:40");
    expect(keys).not.toContain("day:150");
    // The breakpoints themselves survive.
    expect(keys).toContain("t_F");
    expect(keys).toContain("t_F2");
  });

  it("keeps a day that a longer Flood does reach", () => {
    const halfYear = {
      ...solved,
      params: { ...solved.params, t_F2: solved.params.t_F + 100 / DAYS_PER_YEAR },
    } as Calibration;
    const keys = markersFor(halfYear).map((m) => m.key);
    expect(keys).toContain("day:40");
    expect(keys).not.toContain("day:150");
  });
});
