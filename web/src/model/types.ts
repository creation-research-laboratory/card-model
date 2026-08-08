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

/** The eight parameters of `card.models.GeneralModelParams`, in linear units. */
export interface GeneralParams {
  readonly lambda_c: number;
  readonly lambda_F: number;
  readonly lambda_bg: number;
  readonly k_c: number;
  readonly k_F: number;
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
   * rather than computed by the model. Interpolated values are good to ~0.3%
   * on a forward age and ~0.03% on an inverse one — fine for a chart, too
   * coarse to present as an exact figure. The UI should mark them.
   */
  readonly exact: boolean;
  /** Set when the calibration came from a named preset. */
  readonly presetKey?: string;
}

/** Sampled curve. Parallel arrays rather than objects: this gets large. */
export interface Series {
  /** AGEs, ascending. */
  readonly trueAge: readonly number[];
  /** Apparent secular age at each `trueAge`. */
  readonly secularAge: readonly number[];
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

export function presetKeyFor(request: CalibrationRequest): string {
  return `${request.chronology}:${request.boundary}`;
}
