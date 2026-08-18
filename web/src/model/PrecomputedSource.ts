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
  type GeologicColumn,
  type LambdaSeries,
  type Series,
  UnsupportedRequestError,
  hasOverrides,
  presetKeyFor,
} from "./types.js";

/** Shape of `public/precomputed.json`, as written by generate_precomputed.py. */
/**
 * The arrays a preset's charts plot, fetched separately from the index.
 *
 * Split out because seventy presets carry 3.8 MB of curve between them and the
 * index is awaited before the first paint.
 */
export interface PresetBody {
  series: { true_age: number[]; secular_age: number[] };
  lambda_history: { date: number[]; lambda: number[] };
  geologic_column: Array<{
    name: string; rank: string;
    base_secular_age: number; top_secular_age: number;
    in_range: boolean;
    base_true_age?: number; top_true_age?: number;
    duration_true?: number; acceleration?: number | null;
  }>;
}

export type BodyLoader = (key: string) => Promise<PresetBody>;

/** `masoretic:kpg:default` -> `presets/masoretic-kpg-default.json`. */
export function bodyFileName(key: string): string {
  return `${key.replace(/:/g, "-")}.json`;
}

/** Fetches from the same base the index came from. */
export function defaultBodyLoader(base = "./"): BodyLoader {
  return async (key) => {
    const url = `${base}presets/${bodyFileName(key)}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(
        `could not load ${url}: ${response.status} ${response.statusText}`,
      );
    }
    return (await response.json()) as PresetBody;
  };
}

export interface PrecomputedData {
  generator: { card_version: string; series_points: number; lambda_points: number };
  defaults: { chronology: string; boundary: string; mode: string; ice_age: string };
  ice_age_offsets: {
    default: string;
    /** Per-chronology, because each one's own Ice Age date differs. */
    options: Record<string, {
      label: string;
      years_after_flood: Record<string, number>;
    }>;
  };
  chronologies: Record<string, {
    label: string;
    provisional: boolean;
    age_of_earth: number;
    flood_start_date: number;
    flood_end_date: number;
    ice_age_end_date: number;
    flood_start_age: number;
    post_flood_boundary_age: number;
    ice_age_end_age: number;
  }>;
  boundaries: Record<string, { label: string; secular_age: number; uncertainty: number }>;
  calibration: {
    flood_start: { label: string; secular_age: number; uncertainty: number };
    ice_age_end: { label: string; secular_age: number; uncertainty: number };
  };
  flood_duration_years: number;
  /**
   * The parameter form, per mode and chronology, emitted by the same
   * `to_json_schema` call the live source would make. Present here so the
   * panel can render before Pyodide has booted — the controls are what tell a
   * reader the download is worth starting.
   */
  modes: Record<string, {
    label: string;
    enabled: boolean;
    by_chronology: Record<string, {
      schema: { properties: Record<string, {
        title: string; description: string; default: number;
        minimum: number; maximum: number;
        "x-unit": string; "x-log-scale": boolean; "x-is-date": boolean;
      }> };
      free: string[];
      fixed: Record<string, number>;
    }>;
  } | string[]>;
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
    /**
     * The handover value: what the in-Flood exponential has fallen to by
     * `t_F2`, and so the amplitude the post-Flood one starts from. Pinned by
     * continuity rather than free — see `GeneralModelParams.lambda_F2`.
     */
    lambda_F2: number;
    /** Which Ice Age offset this was solved for; see `ice_age_offsets`. */
    ice_age: string;
  }>;
  ics: { version: string; url: string; reviewed: boolean;
    units: Array<{ name: string; rank: string; base_secular_age: number }>;
  };
}

export class PrecomputedSource implements ModelSource {
  readonly kind: SourceKind = "precomputed";
  readonly exact = false;

  /** Arrays fetched per preset, keyed by preset key. */
  private readonly bodies = new Map<string, PresetBody>();

  /**
   * @param data   the index: every preset's metadata, no curves.
   * @param loadBody fetches one preset's arrays. Injectable because Node tests
   *   have no `fetch` for local files, and because the deploy serves the app
   *   from a sub-path.
   */
  constructor(
    private readonly data: PrecomputedData,
    private readonly loadBody: BodyLoader = defaultBodyLoader(),
  ) {}

  /**
   * Fetch and cache one preset's arrays.
   *
   * Seventy presets carry 3.8 MB of curve between them. Shipping them in the
   * index would put that in front of the first paint, which is the one thing
   * this layer exists to avoid — so a preset's curves arrive when it is
   * chosen, ~20 kB gzipped, and are kept for the rest of the session.
   */
  private async body(key: string): Promise<PresetBody> {
    const cached = this.bodies.get(key);
    if (cached) return cached;
    const loaded = await this.loadBody(key);
    this.bodies.set(key, loaded);
    return loaded;
  }

  /** Load from a URL. ~57 kB gzipped, so this is a fetch rather than a download. */
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

  /** Names the package considers free to vary (`ParamSpec.is_fittable`). */
  get fittable(): string[] {
    return (this.data.modes["$fittable"] as string[]) ?? [];
  }

  /** The parameter form for one mode under one chronology, or null. */
  schemaFor(mode: string, chronology: string) {
    const entry = this.data.modes[mode];
    if (!entry || Array.isArray(entry)) return null;
    return entry.by_chronology[chronology] ?? null;
  }

  /** Modes the app should offer. `general` ships authored but disabled. */
  get enabledModes(): string[] {
    return Object.entries(this.data.modes)
      .filter(([k, v]) => !k.startsWith("$") && !Array.isArray(v) && v.enabled)
      .map(([k]) => k);
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

    // Everything downstream (series, lambdaHistory, geologicColumn, the two
    // age conversions) reads the arrays synchronously from the cache, so they
    // are fetched here, once, before any of them can be called.
    await this.body(key);

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
    // `points` is ignored on purpose: resampling at higher density would
    // interpolate, and manufacture precision the table does not have.
    //
    // `exact: true` because these sample values did come from the model — the
    // generator called `forward_age` at exactly these ages. What is inexact
    // about this source is `forwardAge`/`inverseAge` at an *arbitrary* age,
    // which interpolates between rows; `Calibration.exact` governs that.
    return {
      trueAge: preset.series.true_age,
      secularAge: preset.series.secular_age,
      exact: true,
    };
  }

  async lambdaHistory(calibration: Calibration): Promise<LambdaSeries> {
    const preset = this.presetFor(calibration);
    // Returned as generated, not resampled. The step at the Flood is carried
    // by an adjacent pair of samples; interpolating between them would turn
    // the jump this curve exists to show back into a ramp.
    return {
      date: preset.lambda_history.date,
      lambda: preset.lambda_history.lambda,
      floodStartDate: preset.params.t_F,
      floodEndDate: preset.params.t_F2,
      presentDate: calibration.chronology.ageOfEarth,
      exact: true,
    };
  }

  async geologicColumn(calibration: Calibration): Promise<GeologicColumn> {
    const preset = this.presetFor(calibration);
    // Exact, unlike everything else this source derives from its curve: the
    // generator ran the real solver for these. Durations are differences of
    // inverse ages agreeing to four or five significant figures, and
    // interpolating them would put 13.7% error on the Silurian.
    return {
      units: preset.geologic_column.map((u) => ({
        name: u.name,
        rank: u.rank,
        baseSecularAge: u.base_secular_age,
        topSecularAge: u.top_secular_age,
        inRange: u.in_range,
        baseTrueAge: u.base_true_age,
        topTrueAge: u.top_true_age,
        durationTrue: u.duration_true,
        acceleration: u.acceleration,
      })),
      maxSecularAge: preset.max_secular_age,
      exact: true,
    };
  }

  /** ICS chart the column was built from, so the UI can cite and caveat it. */
  get icsSource(): PrecomputedData["ics"] {
    return this.data.ics;
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
    const body = this.bodies.get(key);
    if (!body) {
      // Only reachable by hand-building a Calibration; `calibrate()` always
      // loads the body first. Named rather than left as `undefined.series`.
      throw new UnsupportedRequestError(
        `Preset "${key}" has no curves loaded. Call calibrate() first.`,
      );
    }
    return { ...preset, ...body };
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
