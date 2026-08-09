/**
 * The live source: the real `card` package, answering for real.
 *
 * Everything here is a thin translation between the app's camelCase types and
 * `bridge.py`'s JSON. No model logic lives in this file, and none should — the
 * whole point of running Python in the browser is that there is exactly one
 * implementation of the model and it is the tested one.
 */

import type { ModelSource, SourceKind } from "./ModelSource.js";
import type { PrecomputedData } from "./PrecomputedSource.js";
import type { BridgeTransport } from "../worker/transport.js";
import {
  type Calibration,
  type CalibrationRequest,
  type Chronology,
  type Constraint,
  type GeneralParams,
  type LambdaSeries,
  type Series,
  ModelError,
  UnsupportedRequestError,
  presetKeyFor,
} from "./types.js";

/** Static tables the live source needs to turn preset keys into numbers. */
export interface PresetCatalog {
  chronologies: PrecomputedData["chronologies"];
  boundaries: PrecomputedData["boundaries"];
  secondConstraint: PrecomputedData["second_constraint"];
}

interface BridgeError {
  error: { type: string; message: string };
}

export interface ParameterSchema {
  schema: Record<string, unknown>;
  free: string[];
  fixed: Record<string, number>;
  fittable: string[];
}

export class PyodideSource implements ModelSource {
  readonly kind: SourceKind = "live";
  readonly exact = true;

  /** Warnings from the most recent call — the package's own, not ours. */
  lastWarnings: string[] = [];

  constructor(
    private readonly transport: BridgeTransport,
    private readonly catalog: PresetCatalog,
  ) {}

  /** Force the interpreter to start without having a question to ask yet. */
  async boot(): Promise<void> {
    await this.transport.call("boot");
  }

  async environment(): Promise<{
    python: string; cardVersion: string;
    numpyLoaded: boolean; scipyLoaded: boolean;
  }> {
    return this.unwrap(await this.transport.call("environment"));
  }

  /**
   * Parameter metadata for the input form, fetched from the package.
   *
   * Not transcribed into TypeScript, on purpose: adding a parameter to
   * `GeneralModelParams` should make a control appear with no frontend change.
   */
  async schema(chronologyKey: string, fixed: Record<string, number | string>):
    Promise<ParameterSchema> {
    return this.unwrap(await this.transport.call("schema", JSON.stringify({
      chronology: this.chronologyFor(chronologyKey),
      fixed,
    })));
  }

  supports(): boolean {
    // The live source is the one that can answer anything: any chronology, any
    // boundary, any custom parameter set.
    return true;
  }

  async calibrate(request: CalibrationRequest): Promise<Calibration> {
    const chronology = this.chronologyFor(request.chronology);
    const boundary = this.catalog.boundaries[request.boundary];
    if (!boundary) {
      throw new UnsupportedRequestError(
        `Unknown boundary "${request.boundary}". Known: ` +
        `${Object.keys(this.catalog.boundaries).join(", ")}.`,
      );
    }

    const payload = this.unwrap<{
      params: GeneralParams;
      residuals: number[];
      maxAbsResidual: number;
      maxSecularAge: number;
      floodStartAge: number;
      iceAgeEndAge: number;
    }>(await this.transport.call("calibrate", JSON.stringify({
      chronology,
      floodSecularAge: boundary.secular_age,
      secondSecularAge: this.catalog.secondConstraint.secular_age,
      overrides: request.overrides ?? {},
    })));

    const constraints: Constraint[] = [
      {
        label: boundary.label,
        trueAge: payload.floodStartAge,
        secularAge: boundary.secular_age,
        uncertainty: boundary.uncertainty,
      },
      {
        label: this.catalog.secondConstraint.label,
        trueAge: payload.iceAgeEndAge,
        secularAge: this.catalog.secondConstraint.secular_age,
        uncertainty: this.catalog.secondConstraint.uncertainty,
      },
    ];

    return {
      request,
      params: payload.params,
      chronology,
      constraints,
      residuals: payload.residuals,
      maxAbsResidual: payload.maxAbsResidual,
      maxSecularAge: payload.maxSecularAge,
      exact: true,
      presetKey: request.overrides ? undefined : presetKeyFor(request),
    };
  }

  async series(calibration: Calibration, points = 400): Promise<Series> {
    const payload = this.unwrap<{ trueAge: number[]; secularAge: number[] }>(
      await this.transport.call("series", JSON.stringify({
        chronology: calibration.chronology,
        params: calibration.params,
        points,
        anchors: calibration.constraints.map((c) => c.trueAge),
      })),
    );
    return { trueAge: payload.trueAge, secularAge: payload.secularAge, exact: true };
  }

  async lambdaHistory(calibration: Calibration, points = 400): Promise<LambdaSeries> {
    const payload = this.unwrap<{
      date: number[]; lambda: number[];
      floodStartDate: number; floodEndDate: number; presentDate: number;
    }>(await this.transport.call("lambda_history", JSON.stringify({
      chronology: calibration.chronology,
      params: calibration.params,
      points,
    })));
    return { ...payload, exact: true };
  }

  async forwardAge(calibration: Calibration, trueAge: number): Promise<number> {
    const payload = this.unwrap<{ value: number }>(
      await this.transport.call("forward_age", JSON.stringify({
        chronology: calibration.chronology,
        params: calibration.params,
        trueAge,
      })),
    );
    return payload.value;
  }

  async inverseAge(calibration: Calibration, secularAge: number): Promise<number> {
    const payload = this.unwrap<{ value: number }>(
      await this.transport.call("inverse_age", JSON.stringify({
        chronology: calibration.chronology,
        params: calibration.params,
        secularAge,
      })),
    );
    return payload.value;
  }

  async dispose(): Promise<void> {
    await this.transport.dispose();
  }

  private chronologyFor(key: string): Chronology {
    const spec = this.catalog.chronologies[key];
    if (!spec) {
      throw new UnsupportedRequestError(
        `Unknown chronology "${key}". Known: ` +
        `${Object.keys(this.catalog.chronologies).join(", ")}.`,
      );
    }
    return {
      ageOfEarth: spec.age_of_earth,
      floodStartDate: spec.flood_start_date,
      floodEndDate: spec.flood_end_date,
      iceAgeEndDate: spec.ice_age_end_date,
    };
  }

  /**
   * Turn a bridge response into a value or a throw.
   *
   * `bridge.py` reports failure as data rather than letting an exception cross
   * the boundary, so the package's own error prose survives the trip. It
   * explains the DATE/AGE distinction and why a rate below 1 is meaningless;
   * re-wording it here would be strictly worse.
   */
  private unwrap<T>(json: string): T {
    const payload = JSON.parse(json) as T & Partial<BridgeError> & { warnings?: string[] };
    if (payload.error) {
      throw new ModelError(payload.error.message);
    }
    this.lastWarnings = payload.warnings ?? [];
    return payload as T;
  }
}
