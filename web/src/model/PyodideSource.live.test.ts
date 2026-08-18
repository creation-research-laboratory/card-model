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
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { PrecomputedSource, type PrecomputedData } from "./PrecomputedSource.js";
import { diskBodyLoader, presetWithBody } from "./testData.js";
import { PyodideSource } from "./PyodideSource.js";
import { ModelError, type CalibrationRequest } from "./types.js";
import { DirectTransport } from "../worker/transport.js";

const WEB = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const WHEEL = "card_model-0.1.0-py3-none-any.whl";

const data = JSON.parse(
  readFileSync(join(WEB, "public", "precomputed.json"), "utf8"),
) as PrecomputedData;

const preset = (
  chronology: string, boundary: string, iceAge = "default",
): CalibrationRequest => ({ chronology, boundary, iceAge, mode: "flood_only" });

let live: PyodideSource;
let precomputed: PrecomputedSource;

/**
 * An interpreter that can `import card`.
 *
 * Hardcoding `.venv/bin/python` passed locally and failed in CI with ENOENT:
 * the workflow installs the package with `actions/setup-python` and
 * `pip install -e .`, so `card` is importable from `python3` on PATH and there
 * is no virtualenv at all. Probing rather than guessing covers both, and fails
 * with something actionable instead of ENOENT when it covers neither.
 */
async function pythonWithCard(): Promise<string> {
  const candidates = [
    process.env.CARD_PYTHON,
    join(WEB, "..", ".venv", "bin", "python"),
    "python3",
    "python",
  ].filter((c): c is string => Boolean(c));

  for (const bin of candidates) {
    try {
      execFileSync(bin, ["-c", "import card"], { stdio: "ignore" });
      return bin;
    } catch {
      // Missing interpreter, or one without the package. Try the next.
    }
  }
  throw new Error(
    `no Python with \`card\` importable (tried ${candidates.join(", ")}). ` +
    "Install it with `pip install -e .`, or set CARD_PYTHON.",
  );
}

/** Relative agreement, with an absolute fallback for values at or near zero. */
function closeEnough(a: number, b: number, tolerance = 1e-8): boolean {
  const scale = Math.max(Math.abs(a), Math.abs(b));
  return scale < 1e-12 ? Math.abs(a - b) < 1e-12 : Math.abs(a - b) / scale < tolerance;
}

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
    calibration: data.calibration,
            iceAgeOffsets: data.ice_age_offsets.options,
    floodDurationYears: data.flood_duration_years,
    geologicUnits: data.ics.units.map((u) => ({
              name: u.name, rank: u.rank, baseSecularAge: u.base_secular_age,
            })),
  });
  precomputed = new PrecomputedSource(data, diskBodyLoader);
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
    expect(cal.params.lambda_F / 4.54657e9 - 1).toBeCloseTo(0, 4);
    // Two rates now, three orders of magnitude apart. Pinning both is the
    // point: swapping them would look plausible and be badly wrong.
    expect(cal.params.k_F).toBeCloseTo(9.571, 2);
    expect(cal.params.k_PF).toBeCloseTo(0.00480302, 7);
    expect(cal.maxAbsResidual).toBeLessThan(1e-12);
    expect(cal.exact).toBe(true);
  });

  it("solves every preset to machine precision", async () => {
    for (const key of precomputed.presetKeys) {
      const p = presetWithBody(key);
      const cal = await live.calibrate(preset(p.chronology, p.boundary, p.ice_age));
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
      const p = presetWithBody(key);
      const request = preset(p.chronology, p.boundary, p.ice_age);
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

    // These are the numbers the UI's "≈" is promising, so they are asserted
    // rather than assumed. The inverse is the looser of the two because the
    // curve's knee just after the Flood is sharp, and inverting a sharp knee
    // is ill-conditioned.
    // Measured on the shipped grid across all 70 presets: 0.98% forward, at
    // septuagint:pt:y700. It was 0.77% before the Ice Age offsets, and 4.2%
    // between adding them and sizing the refinement window from both
    // relaxation rates — this assertion is what caught that.
    expect(worstForward).toBeLessThan(1.5e-2);
    expect(worstInverse).toBeLessThan(1.5e-2);
  });

  it("agrees exactly on the solved parameters, which are not interpolated", async () => {
    // Only curve values are approximate. The generator ran the real solver for
    // the parameters and residuals, so those should match to the last digit
    // the file stores.
    for (const key of precomputed.presetKeys) {
      const p = presetWithBody(key);
      const request = preset(p.chronology, p.boundary, p.ice_age);
      const liveCal = await live.calibrate(request);
      const preCal = await precomputed.calibrate(request);
      expect(preCal.params.lambda_F / liveCal.params.lambda_F - 1).toBeCloseTo(0, 8);
      expect(preCal.maxSecularAge / liveCal.maxSecularAge - 1).toBeCloseTo(0, 8);
    }
  });
});

describe("lambda history agrees between the two sources", () => {
  it("matches the precomputed curve wherever the two grids coincide", async () => {
    const request = preset("masoretic", "kpg");
    const liveCal = await live.calibrate(request);
    const preCal = await precomputed.calibrate(request);
    const pre = await precomputed.lambdaHistory(preCal);
    const liveHistory = await live.lambdaHistory(liveCal, data.generator.lambda_points);

    // Neither an exact length match nor nearest-neighbour matching. The file
    // rounds dates to 9 significant figures, which merges a couple of samples
    // the live grid keeps distinct; and just past t_F lambda falls fast enough
    // that pairing a sample with its *neighbour* rather than itself shifts
    // lambda by ~1e-5. So compare only where the dates genuinely coincide, and
    // require that to be nearly all of them.
    const liveAt = new Map<string, number>();
    liveHistory.date.forEach((d, i) => {
      liveAt.set(d.toPrecision(9), liveHistory.lambda[i]);
    });

    let compared = 0;
    for (let i = 0; i < pre.date.length; i++) {
      const match = liveAt.get(pre.date[i].toPrecision(9));
      if (match === undefined) continue;
      compared++;
      // 1e-4, and the floor is arithmetic rather than arbitrary: the file
      // stores dates to 9 significant figures, so a date near 1656 carries
      // ~1e-6 yr of rounding, and k_F ~ 10/yr turns that into ~1e-5 of relative
      // error in lambda. It was 1e-8 when k_F was 0.005; the tolerance has to
      // track the calibration, so this leaves an order of magnitude of room.
      expect(closeEnough(match, pre.lambda[i], 1e-4)).toBe(true);
    }
    expect(compared).toBeGreaterThan(pre.date.length * 0.9);
  });

  it("steps at the Flood in the live source too", async () => {
    const cal = await live.calibrate(preset("masoretic", "kpg"));
    const history = await live.lambdaHistory(cal);
    const i = history.date.findIndex((d) => d === cal.params.t_F);
    expect(i).toBeGreaterThan(-1);
    expect(history.lambda[i]).toBeCloseTo(1, 9);
    // The sample past the step has already relaxed a little, so compare
    // against the decay the model predicts over that gap rather than against
    // lambda_F itself — an absolute tolerance is meaningless at 1e9.
    const gap = history.date[i + 1] - cal.params.t_F;
    const expected = cal.params.lambda_F * Math.exp(-cal.params.k_F * gap);
    expect(closeEnough(history.lambda[i + 1], expected, 1e-6)).toBe(true);
  });

  it("reflects a Creation-week override the age curve barely shows", async () => {
    // lambda(t) is where the Creation-week parameters are actually visible;
    // they leave both constraints untouched, so the age curve's fitted region
    // does not move at all.
    const cal = await live.calibrate({
      ...preset("masoretic", "kpg"), overrides: { lambda_c: 1e6, k_c: 1e-2 },
    });
    const history = await live.lambdaHistory(cal);
    expect(history.lambda[0]).toBeCloseTo(1e6, -1);
  });
});

describe("geologic column agrees between the two sources", () => {
  it("matches the precomputed column unit for unit", async () => {
    for (const key of precomputed.presetKeys) {
      const p = presetWithBody(key);
      const request = preset(p.chronology, p.boundary, p.ice_age);
      const liveCol = await live.geologicColumn(await live.calibrate(request));
      const preCol = await precomputed.geologicColumn(
        await precomputed.calibrate(request));

      expect(liveCol.units.length).toBe(preCol.units.length);
      for (let i = 0; i < preCol.units.length; i++) {
        const a = liveCol.units[i];
        const b = preCol.units[i];
        expect(a.name).toBe(b.name);
        expect(a.inRange).toBe(b.inRange);
        if (!a.inRange) continue;
        // 1e-8 relative: the file rounds to 9 significant figures.
        expect(closeEnough(a.durationTrue!, b.durationTrue!, 1e-7)).toBe(true);
        expect(closeEnough(a.acceleration!, b.acceleration!, 1e-7)).toBe(true);
      }
    }
  });

  it("recomputes the column for custom parameters", async () => {
    // The precomputed layer cannot answer this at all, which is the whole
    // reason the live source implements it too.
    const request: CalibrationRequest = {
      ...preset("masoretic", "kpg"), overrides: { lambda_F: 8.0e9 },
    };
    expect(precomputed.supports(request)).toBe(false);

    const overridden = await live.calibrate(request);
    const column = await live.geologicColumn(overridden);
    expect(column.units.every((u) => u.inRange)).toBe(true);

    const base = await live.calibrate(preset("masoretic", "kpg"));
    const baseColumn = await live.geologicColumn(base);

    // A larger lambda_F raises the ceiling — that much is monotone, because
    // the apparent age at the onset is the whole integral and lambda_F scales
    // it. Individual durations are NOT monotone in lambda_F: lifting the curve
    // moves each unit's base to a different point inside the Flood year, where
    // the in-Flood relaxation has already brought lambda down, so a unit can
    // end up either shorter or longer. Asserting otherwise was a wrong guess.
    expect(overridden.maxSecularAge).toBeGreaterThan(base.maxSecularAge);

    // What the override must do is change the column at all — otherwise the
    // live source would be handing back the preset regardless.
    const cambrian = (c: typeof column) =>
      c.units.find((u) => u.name === "Cambrian")!.durationTrue!;
    expect(cambrian(column)).not.toBeCloseTo(cambrian(baseColumn), 6);
  });
});

describe("custom parameters — the thing only the live source can do", () => {
  it("accepts an override the precomputed layer must refuse", async () => {
    const request: CalibrationRequest = {
      ...preset("masoretic", "kpg"), overrides: { lambda_F: 5.0e9 },
    };
    expect(precomputed.supports(request)).toBe(false);

    const cal = await live.calibrate(request);
    expect(cal.params.lambda_F / 5.0e9 - 1).toBeCloseTo(0, 6);
    // Both rates still come from the solve; only what was overridden changed.
    expect(cal.params.k_F).toBeCloseTo(9.571, 2);
    expect(cal.params.k_PF).toBeCloseTo(0.00480302, 7);
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

describe("residuals describe the model on screen", () => {
  it("reports machine precision only while nothing is overridden", async () => {
    const cal = await live.calibrate(preset("masoretic", "kpg"));
    expect(cal.maxAbsResidual).toBeLessThan(1e-12);
  });

  it("recomputes them once a fitted parameter is moved", async () => {
    // The bug this pins: residuals used to be taken from the solve, which runs
    // *before* overrides are applied. Moving lambda_F then left the readout
    // claiming an exact fit for a curve that missed every constraint. Free
    // parameters are exactly what made that reachable.
    const base = await live.calibrate(preset("masoretic", "kpg"));
    const moved = await live.calibrate({
      ...preset("masoretic", "kpg"),
      overrides: { lambda_F: base.params.lambda_F * 1.66 },
    });
    expect(moved.maxAbsResidual).toBeGreaterThan(0.1);

    // And the reported residuals match what the model actually produces.
    for (let i = 0; i < moved.constraints.length; i++) {
      const c = moved.constraints[i];
      const got = await live.forwardAge(moved, c.trueAge);
      expect(moved.residuals[i]).toBeCloseTo(got / c.secularAge - 1, 9);
    }
  });

  it("still reports exact for a Creation-week override", async () => {
    // lambda_c and k_c do not enter any constraint — every constraint age maps
    // to a formation DATE at or after t_F — so the fit is genuinely untouched.
    // This is what the recompute must NOT break.
    const cal = await live.calibrate({
      ...preset("masoretic", "kpg"),
      overrides: { lambda_c: 1e8, k_c: 1e-3 },
    });
    expect(cal.maxAbsResidual).toBeLessThan(1e-12);
  });
});

describe("the CSV download", () => {
  const STAMP = new Date("2026-08-17T12:00:00Z");

  async function csvFor(boundary: string, points = 60) {
    const cal = await live.calibrate(preset("masoretic", boundary));
    return live.csv(cal, { points, generated: STAMP, description: "test" });
  }

  it("is byte-identical to what `card series` writes", async () => {
    // The claim the whole module exists to support: one function behind the
    // CLI and the download, so a file fetched from the site and one produced
    // locally are the same bytes. Both sides are given the same timestamp,
    // which is the only value in the file not derived from the model.
    const cal = await live.calibrate(preset("masoretic", "kpg"));
    const fromBrowser = await live.csv(cal, {
      points: 60, generated: STAMP, description: "parity check",
    });

    const script = [
      "import json, sys",
      "from datetime import datetime, timezone",
      "from card.chronology import Chronology",
      "from card.models import GeneralModel, GeneralModelParams",
      "from card.series import SeriesConstraint, to_csv",
      "req = json.loads(sys.stdin.read())",
      "c = req['chronology']",
      "chron = Chronology(age_of_earth=c['ageOfEarth'],",
      "                   flood_start_date=c['floodStartDate'],",
      "                   flood_end_date=c['floodEndDate'],",
      "                   ice_age_end_date=c['iceAgeEndDate'])",
      "model = GeneralModel(GeneralModelParams.from_dict(req['params']))",
      "cons = [SeriesConstraint(x['label'], x['trueAge'], x['secularAge'], x['residual'])",
      "        for x in req['constraints']]",
      "sys.stdout.write(to_csv(model, chron, points=60, constraints=cons,",
      "    description='parity check',",
      "    generated=datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)))",
    ].join("\n");

    const fromPython = execFileSync(
      await pythonWithCard(), ["-c", script],
      {
        encoding: "utf8",
        input: JSON.stringify({
          chronology: cal.chronology,
          params: cal.params,
          constraints: cal.constraints.map((x, i) => ({
            label: x.label, trueAge: x.trueAge, secularAge: x.secularAge,
            residual: cal.residuals[i],
          })),
        }),
      },
    );

    expect(fromBrowser).toBe(fromPython);
  });

  it("puts every constraint on an exact row", async () => {
    const text = await csvFor("kpg");
    const cal = await live.calibrate(preset("masoretic", "kpg"));
    const body = text.split("\n").filter((l) => l && !l.startsWith("#"));
    const ages = body.slice(1).map((l) => Number(l.split(",")[0]));
    for (const c of cal.constraints) expect(ages).toContain(c.trueAge);
  });

  it("carries enough provenance to rebuild the model", async () => {
    // With free parameters most downloads describe a model that exists
    // nowhere else, so a file without its chronology is an unreproducible
    // number.
    const text = await csvFor("kpg");
    for (const field of ["age_of_earth", "lambda_F=", "k_F=", "k_PF=", "t_F2="]) {
      expect(text).toContain(field);
    }
    expect(text).toMatch(/# constraint:.*residual/);
  });

  it("follows the boundary it was calibrated for", async () => {
    const [kpg, nq] = await Promise.all([csvFor("kpg"), csvFor("nq")]);
    expect(kpg).not.toBe(nq);
    expect(kpg).toContain("66000000.0 yr apparent");
    expect(nq).toContain("2580000.0 yr apparent");
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

  it("describes the fit with as many constraints as it has residuals", async () => {
    // The live source used to build two Constraint objects while the bridge
    // returned three residuals, so `residuals[2]` -- the Ice Age -- had no
    // constraint beside it. Anything zipping the two lists silently dropped
    // the third pair, and the readout reported two thirds of the fit as if it
    // were all of it.
    const cal = await live.calibrate(preset("masoretic", "kpg"));
    expect(cal.constraints).toHaveLength(cal.residuals.length);
    expect(cal.constraints).toHaveLength(3);
  });

  it("agrees with the precomputed source on what was fitted", async () => {
    // Both sources answer the same question, so they must describe the same
    // three pairs -- same labels, same ages. The markers read these labels to
    // name the boundary, so a divergence here would show up on the chart.
    for (const boundary of ["kpg", "nq"] as const) {
      const request = preset("masoretic", boundary);
      const [liveCal, preCal] = await Promise.all([
        live.calibrate(request), precomputed.calibrate(request),
      ]);
      expect(liveCal.constraints.map((c) => c.label))
        .toEqual(preCal.constraints.map((c) => c.label));
      for (let i = 0; i < liveCal.constraints.length; i++) {
        expect(liveCal.constraints[i].trueAge)
          .toBeCloseTo(preCal.constraints[i].trueAge, 6);
        expect(liveCal.constraints[i].secularAge)
          .toBeCloseTo(preCal.constraints[i].secularAge, 6);
      }
    }
  });

  it("rejects a combination no single slider bound could prevent", async () => {
    // The one the UI actually has to handle. Every control is clamped to its
    // own spec, so a lone parameter cannot leave its range — but `t_c` and
    // `t_F` are independently draggable across the same interval, and the
    // model requires t_c <= t_F <= t_F2. Nothing about a per-parameter bound
    // catches that, which is why the panel shows the package's prose.
    const rejected = live.calibrate({
      ...preset("masoretic", "kpg"),
      overrides: { t_c: 3000, t_F: 1656 },
    });
    await expect(rejected).rejects.toThrow(ModelError);
    // The explanation, not just the complaint.
    await expect(rejected).rejects.toThrow(/must be ordered/);
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
    // k_PF joins the free set: the flood-only mode pins the Creation-week
    // parameters and the dates, and both relaxation rates are now fitted.
    expect(result.free.sort()).toEqual(
      ["k_F", "k_PF", "lambda_F", "lambda_bg"].sort());
    // lambda_bg is present but not fittable (minimum == maximum), so a UI skips
    // it structurally rather than by a hardcoded exclusion.
    expect(result.fittable).not.toContain("lambda_bg");
    expect(result.fixed.t_F).toBe(1656);
  });

  it("resolves chronology names so a mode works across chronologies", async () => {
    const result = await live.schema("septuagint", {
      t_F: "flood_start_date", t_F2: "flood_end_date",
    });
    expect(result.fixed.t_F).toBe(2176);
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
