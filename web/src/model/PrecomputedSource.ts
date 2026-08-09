/**
 * The first-paint layer: six presets, solved by `card` in CI, read from a
 * static table.
 *
 * This is **not** an optimization. Pyodide is 5.84 MB and boot is essentially
 * all download — 42 s at a measured 142 kB/s, ~12 s at 4 Mbps. For that whole
 * window this class is the entire application as far as a first-time visitor is
 * concerned, so it is built and tested as a real code path.
 *
 * What it cannot do is solve. It holds the presets the generator produced; a
 * request with custom parameters gets `UnsupportedRequestError`, and the
 * caller's response is to boot the live source and wait.
 */

import type { ModelSource, SourceKind } from "./ModelSource.js";
import { interpolateLogLog, invertLogLog } from "./interpolate.js";
import {
  type Calibration,
  type CalibrationRequest,
  type Chronology,
  type Constraint,
  type GeneralParams,
  type Series,
  UnsupportedRequestError,
  hasOverrides,
  presetKeyFor,
} from "./types.js";

/** Shape of `public/precomputed.json`, as written by generate_precomputed.py. */
export interface PrecomputedData {
  generator: { card_version: string; series_points: number };
  defaults: { chronology: string; boundary: string; mode: string };
  chronologies: Record<string, {
    label: string;
    provisional: boolean;
    age_of_earth: number;
    flood_start_date: number;
    flood_end_date: number;
    ice_age_end_date: number;
    flood_start_age: number;
    ice_age_end_age: number;
  }>;
  boundaries: Record<string, { label: string; secular_age: number; uncertainty: number }>;
  second_constraint: { label: string; secular_age: number; uncertainty: number };
  presets: Record<string, {
    chronology: string;
    boundary: string;
    label: string;
    mode: string;
    params: GeneralParams;
    residuals: number[];
    max_abs_residual: number;
    max_secular_age: number;
    constraints: Array<{
      label: string; true_age: number; secular_age: number; uncertainty: number;
    }>;
    series: { true_age: number[]; secular_age: number[] };
  }>;
}

export class PrecomputedSource implements ModelSource {
  readonly kind: SourceKind = "precomputed";
  readonly exact = false;

  constructor(private readonly data: PrecomputedData) {}

  /** Load from a URL. The file is ~26 kB gzipped, so this is a cheap fetch. */
  static async load(url = "./precomputed.json"): Promise<PrecomputedSource> {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`could not load ${url}: ${response.status} ${response.statusText}`);
    }
    return new PrecomputedSource((await response.json()) as PrecomputedData);
  }

  get generatedBy(): PrecomputedData["generator"] {
    return this.data.generator;
  }

  get defaults(): PrecomputedData["defaults"] {
    return this.data.defaults;
  }

  /** Preset keys this source can answer, for a UI that lists them. */
  get presetKeys(): string[] {
    return Object.keys(this.data.presets);
  }

  supports(request: CalibrationRequest): boolean {
    if (hasOverrides(request)) return false;
    const preset = this.data.presets[presetKeyFor(request)];
    return !!preset && preset.mode === request.mode;
  }

  async calibrate(request: CalibrationRequest): Promise<Calibration> {
    const key = presetKeyFor(request);
    const preset = this.data.presets[key];

    if (hasOverrides(request)) {
      throw new UnsupportedRequestError(
        "The precomputed layer holds solved presets and cannot solve custom " +
        "parameters. Boot the live source (ensureLive) and retry there.",
      );
    }
    if (!preset) {
      throw new UnsupportedRequestError(
        `No precomputed preset "${key}". Known: ${this.presetKeys.join(", ")}.`,
      );
    }
    if (preset.mode !== request.mode) {
      throw new UnsupportedRequestError(
        `Preset "${key}" was generated for mode "${preset.mode}", not ` +
        `"${request.mode}".`,
      );
    }

    const chron = this.data.chronologies[preset.chronology];
    const chronology: Chronology = {
      ageOfEarth: chron.age_of_earth,
      floodStartDate: chron.flood_start_date,
      floodEndDate: chron.flood_end_date,
      iceAgeEndDate: chron.ice_age_end_date,
    };
    const constraints: Constraint[] = preset.constraints.map((c) => ({
      label: c.label,
      trueAge: c.true_age,
      secularAge: c.secular_age,
      uncertainty: c.uncertainty,
    }));

    return {
      request,
      params: preset.params,
      chronology,
      constraints,
      residuals: preset.residuals,
      maxAbsResidual: preset.max_abs_residual,
      maxSecularAge: preset.max_secular_age,
      // The solved parameters and residuals are exact — the generator ran the
      // real solver. Only curve values are interpolated, and `exact: false`
      // governs those, so it is the honest flag for the object as a whole.
      exact: false,
      presetKey: key,
    };
  }

  async series(calibration: Calibration): Promise<Series> {
    const preset = this.presetFor(calibration);
    // `points` is ignored on purpose: resampling an interpolated table at
    // higher density would manufacture precision the data does not have.
    return {
      trueAge: preset.series.true_age,
      secularAge: preset.series.secular_age,
      exact: false,
    };
  }

  async forwardAge(calibration: Calibration, trueAge: number): Promise<number> {
    const preset = this.presetFor(calibration);
    this.checkAge(trueAge, "trueAge", calibration.chronology.ageOfEarth);
    return interpolateLogLog(
      preset.series.true_age, preset.series.secular_age, trueAge,
    );
  }

  async inverseAge(calibration: Calibration, secularAge: number): Promise<number> {
    const preset = this.presetFor(calibration);
    this.checkAge(secularAge, "secularAge", calibration.maxSecularAge);
    return invertLogLog(
      preset.series.true_age, preset.series.secular_age, secularAge,
    );
  }

  private presetFor(calibration: Calibration) {
    const key = calibration.presetKey ?? presetKeyFor(calibration.request);
    const preset = this.data.presets[key];
    if (!preset) {
      throw new UnsupportedRequestError(
        `No precomputed preset "${key}"; this calibration did not come from ` +
        "this source.",
      );
    }
    return preset;
  }

  /**
   * Mirror the package's domain checks rather than clamping.
   *
   * `card` raises ValueError for an out-of-domain age and never returns a
   * plausible number for nonsense input. The precomputed layer stands in for
   * that model, so it has to refuse the same inputs — otherwise the app's
   * behavior would change under it when the live source swaps in.
   */
  private checkAge(value: number, name: string, maximum: number): void {
    if (!Number.isFinite(value)) {
      throw new RangeError(`${name} must be finite, got ${value}`);
    }
    if (value < 0) {
      throw new RangeError(
        `${name} must be >= 0, got ${value}. Ages count years before present.`,
      );
    }
    if (value > maximum) {
      throw new RangeError(
        `${name} (${value}) exceeds the maximum this model can produce ` +
        `(${maximum}).`,
      );
    }
  }
}
