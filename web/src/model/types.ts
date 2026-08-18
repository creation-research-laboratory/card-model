/**
 * Shared vocabulary for the model layer.
 *
 * These types mirror the `card` package deliberately closely — the naming rule
 * in particular. A quantity ending in `Age` is an AGE (years before present);
 * one ending in `Date` is a DATE (years after Day 1 of Creation). The two run
 * in opposite directions and a matching pair sums to `ageOfEarth`. Getting this
 * wrong caused a real fitting error in the package's history, which is why the
 * convention is carried into the type names rather than left to comments.
 */

/** Keys into `presets.json`. Strings rather than unions: presets are data. */
export type ChronologyKey = string;
export type BoundaryKey = string;
export type ModeKey = string;

/** A young-earth chronology. All DATEs except `ageOfEarth`, which is an AGE. */
export interface Chronology {
  readonly ageOfEarth: number;
  readonly floodStartDate: number;
  readonly floodEndDate: number;
  readonly iceAgeEndDate: number;
}

/** The nine parameters of `card.models.GeneralModelParams`, in linear units. */
export interface GeneralParams {
  readonly lambda_c: number;
  readonly lambda_F: number;
  readonly lambda_bg: number;
  readonly k_c: number;
  /** Relaxation *during* the Flood, `t_F < t <= t_F2`. Zero is a flat Flood. */
  readonly k_F: number;
  /** Relaxation *after* the Flood, `t > t_F2`. This is what pre-2026-08-09
   * builds called `k_F`, so a value read from an old payload means the wrong
   * phase here. */
  readonly k_PF: number;
  readonly t_c: number;
  readonly t_F: number;
  readonly t_F2: number;
}

/** One matched date pair: an event dated both ways. */
export interface Constraint {
  readonly label: string;
  /** AGE (years before present) at which the event happened. */
  readonly trueAge: number;
  /** The secular age rock formed at that event should appear to have. */
  readonly secularAge: number;
  readonly uncertainty: number;
}

/** What the user asked for. Presence of `overrides` makes it non-preset. */
export interface CalibrationRequest {
  readonly chronology: ChronologyKey;
  readonly boundary: BoundaryKey;
  /** Which Ice Age offset; a key into `ice_age_offsets.options`. */
  readonly iceAge: string;
  readonly mode: ModeKey;
  /**
   * Free-parameter overrides. Any value here means the request is no longer a
   * preset, so only the live source can answer it.
   */
  readonly overrides?: Readonly<Partial<GeneralParams>>;
}

/** A solved model, plus everything needed to describe and reuse it. */
export interface Calibration {
  readonly request: CalibrationRequest;
  readonly params: GeneralParams;
  readonly chronology: Chronology;
  readonly constraints: readonly Constraint[];
  /** Relative misfit per constraint, as `predicted / target - 1`. */
  readonly residuals: readonly number[];
  readonly maxAbsResidual: number;
  /** Largest secular age this model can produce; the domain of `inverseAge`. */
  readonly maxSecularAge: number;
  /**
   * False when these numbers were interpolated from the precomputed table
   * rather than computed by the model. Interpolated values are good to ~0.8%
   * on a forward age and ~0.9% on an inverse one — fine for a chart, too coarse
   * to present as an exact figure. The UI should mark them.
   */
  readonly exact: boolean;
  /** Set when the calibration came from a named preset. */
  readonly presetKey?: string;
}

/**
 * Sampled curve. Parallel arrays rather than objects: this gets large.
 *
 * `exact` here asks a narrower question than `Calibration.exact`: did these
 * sample values come from the model? For both sources they did — the
 * precomputed generator called `forward_age` at exactly these ages. What is
 * approximate about the precomputed source is answering at an *arbitrary* age,
 * which interpolates between rows, and `Calibration.exact` governs that.
 */
export interface Series {
  /** AGEs, ascending. */
  readonly trueAge: readonly number[];
  /** Apparent secular age at each `trueAge`. */
  readonly secularAge: readonly number[];
  readonly exact: boolean;
}

/**
 * Decay-rate history: lambda against DATE.
 *
 * The one curve in the app whose x axis is a DATE (years after Day 1 of
 * Creation) rather than an AGE. It is also the one that genuinely steps —
 * `forward_age` is the integral of a bounded rate and therefore continuous,
 * but lambda itself jumps at t_F, the Flood's onset. It does *not* jump at
 * t_F2: `lambda_F2` is pinned to whatever the in-Flood exponential has reached
 * by then, so the rate changes pace there rather than value. The onset carries
 * two samples so a chart draws its jump rather than a ramp.
 */
export interface LambdaSeries {
  /** DATEs, ascending, from 0 to the present. */
  readonly date: readonly number[];
  /** lambda at each DATE, as a multiple of background. */
  readonly lambda: readonly number[];
  readonly floodStartDate: number;
  readonly floodEndDate: number;
  readonly presentDate: number;
  readonly exact: boolean;
}

/**
 * One chronostratigraphic unit, with its secular span mapped through the model.
 *
 * `inRange` is false when the unit's base is older than the calibration can
 * produce — pinning the Flood to the K/Pg boundary caps the model at 66 Myr, so
 * the Cretaceous and everything older simply has no young-earth date. Reported
 * rather than dropped, so a chart can say the column runs out.
 */
export interface GeologicUnit {
  readonly name: string;
  readonly rank: string;
  /** Older boundary, secular years. */
  readonly baseSecularAge: number;
  /** Younger boundary, secular years. */
  readonly topSecularAge: number;
  readonly inRange: boolean;
  /** AGE of the older boundary. Absent when out of range. */
  readonly baseTrueAge?: number;
  readonly topTrueAge?: number;
  /** Young-earth years the unit occupies. Absent when out of range. */
  readonly durationTrue?: number;
  /** Secular years elapsed per young-earth year across this unit. */
  readonly acceleration?: number | null;
}

export interface GeologicColumn {
  readonly units: readonly GeologicUnit[];
  readonly maxSecularAge: number;
  readonly exact: boolean;
}

/** Thrown when a source is asked for something it structurally cannot answer. */
export class UnsupportedRequestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UnsupportedRequestError";
  }
}

/** Thrown when the model itself rejects the input; carries the package's prose. */
export class ModelError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ModelError";
  }
}

export function hasOverrides(request: CalibrationRequest): boolean {
  return !!request.overrides && Object.keys(request.overrides).length > 0;
}

/**
 * `masoretic:kpg:default`.
 *
 * The Ice Age offset is part of the key because it is part of the solve: the
 * third matched pair fixes `k_PF`, so two requests differing only in that
 * offset are different calibrations, not the same one relabelled.
 */
export function presetKeyFor(request: CalibrationRequest): string {
  return `${request.chronology}:${request.boundary}:${request.iceAge}`;
}
