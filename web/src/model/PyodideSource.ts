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
  type GeologicColumn,
  type GeologicUnit,
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
  /** The two matched pairs: PC/C at the Flood, and the Ice Age endpoint. */
  calibration: PrecomputedData["calibration"];
  /**
   * The ICS unit list, name and base age only. Passed through to `bridge.py`
   * rather than read there: the browser already has it, and `card` has no
   * business knowing about the chronostratigraphic chart.
   */
  geologicUnits: Array<{ name: string; rank: string; baseSecularAge: number }>;
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
      // The two pairs are the ends of the Flood: a fixed pre-Flood/Flood
      // boundary and the selected Flood/post-Flood one.
      floodStartSecularAge: this.catalog.calibration.flood_start.secular_age,
      iceAgeSecularAge: this.catalog.calibration.ice_age_end.secular_age,
      // Not a constraint — passed so the bridge can report where it lands.
      floodEndSecularAge: boundary.secular_age,
      overrides: request.overrides ?? {},
    })));

    const calib = this.catalog.calibration;
    const constraints: Constraint[] = [
      {
        label: `Flood begins — ${calib.flood_start.label}`,
        trueAge: payload.floodStartAge,
        secularAge: calib.flood_start.secular_age,
        uncertainty: 0,
      },
      {
        label: calib.ice_age_end.label,
        trueAge: payload.iceAgeEndAge,
        secularAge: calib.ice_age_end.secular_age,
        uncertainty: 0,
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

  async geologicColumn(calibration: Calibration): Promise<GeologicColumn> {
    const payload = this.unwrap<{ units: GeologicUnit[]; maxSecularAge: number }>(
      await this.transport.call("geologic_column", JSON.stringify({
        chronology: calibration.chronology,
        params: calibration.params,
        units: this.catalog.geologicUnits,
      })),
    );
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
