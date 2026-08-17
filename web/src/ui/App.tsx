/**
 * The app shell.
 *
 * Phase 4 ships presets only — free parameters are Phase 5 — so nothing here
 * needs the live source yet, and Pyodide never starts unless the reader asks
 * for it. That is the loading strategy the Phase 2 measurements forced: 5.84 MB
 * is a fixed cost, and a first-time visitor on a slow connection would be
 * looking at a spinner for 40 seconds.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AgeComparisonChart, type AgeOrientation } from "../charts/AgeComparisonChart.js";
import { GeologicColumnChart } from "../charts/GeologicColumnChart.js";
import { LambdaHistoryChart, type LambdaZoom } from "../charts/LambdaHistoryChart.js";
import { CalibrationReadout } from "./CalibrationReadout.js";
import { ParameterPanel } from "./ParameterPanel.js";
import { PresetPicker } from "./PresetPicker.js";
import { SeriesTable } from "./SeriesTable.js";
import { ModelSourceManager, type ManagerState } from "../model/ModelSourceManager.js";
import { PrecomputedSource, type PrecomputedData } from "../model/PrecomputedSource.js";
import { PyodideSource } from "../model/PyodideSource.js";
import { WorkerTransport } from "../worker/transport.js";
import type {
  Calibration, CalibrationRequest, GeneralParams, GeologicColumn,
  LambdaSeries, Series,
} from "../model/types.js";

interface Props {
  data: PrecomputedData;
}

export function App({ data }: Props) {
  const precomputed = useMemo(() => new PrecomputedSource(data), [data]);

  const manager = useMemo(
    () => new ModelSourceManager({
      precomputed,
      createLive: async () => {
        const worker = new Worker(
          new URL("../worker/pyodide.worker.ts", import.meta.url),
          { type: "module", name: "card-pyodide" },
        );
        return new PyodideSource(
          new WorkerTransport(worker, new URL(import.meta.env.BASE_URL, location.href).href),
          {
            chronologies: data.chronologies,
            boundaries: data.boundaries,
            calibration: data.calibration,
            floodDurationYears: data.flood_duration_years,
            // Every preset carries the same unit list, including the units it
            // cannot reach, so any one of them is a complete catalogue.
            geologicUnits: Object.values(data.presets)[0].geologic_column.map((u) => ({
              name: u.name, rank: u.rank, baseSecularAge: u.base_secular_age,
            })),
          },
        );
      },
    }),
    [precomputed, data],
  );

  // Which boundary, if any, reaches every unit of the geologic column. Read
  // from the data rather than hardcoded, so adding a boundary to presets.json
  // is still a data-only change.
  const fullColumnBoundary = useMemo(() => {
    for (const [key, preset] of Object.entries(data.presets)) {
      if (preset.geologic_column.every((u) => u.in_range)) {
        return { key: preset.boundary, label: data.boundaries[preset.boundary].label };
      }
      void key;
    }
    return null;
  }, [data]);

  const [state, setState] = useState<ManagerState>(manager.state);
  const [request, setRequest] = useState<CalibrationRequest>({
    chronology: data.defaults.chronology,
    boundary: data.defaults.boundary,
    mode: data.defaults.mode,
  });
  const [calibration, setCalibration] = useState<Calibration | null>(null);
  const [series, setSeries] = useState<Series | null>(null);
  const [history, setHistory] = useState<LambdaSeries | null>(null);
  const [column, setColumn] = useState<GeologicColumn | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Which way round the age chart is read. Both directions are the same
  // model; a reader arriving with a published radiometric age wants "true".
  const [orientation, setOrientation] = useState<AgeOrientation>("apparent");
  const [lambdaZoom, setLambdaZoom] = useState<LambdaZoom>("full");

  // Parameter overrides the reader has made. Empty means "the preset as
  // calibrated"; anything in here makes the request non-preset, which only the
  // live source can answer.
  const [overrides, setOverrides] = useState<Partial<GeneralParams>>({});
  const overridden = useMemo(
    () => new Set(Object.keys(overrides)), [overrides],
  );

  // The parameter form, from the package. Available before Pyodide boots
  // because the generator emits it alongside the presets.
  const modeSchema = useMemo(
    () => precomputed.schemaFor(request.mode, request.chronology),
    [precomputed, request.mode, request.chronology],
  );

  useEffect(() => manager.subscribe(setState), [manager]);

  // A Pyodide instance holds ~100 MB; terminating on pagehide is what makes
  // repeated loads deterministic.
  useEffect(() => {
    const dispose = () => void manager.dispose();
    addEventListener("pagehide", dispose);
    return () => removeEventListener("pagehide", dispose);
  }, [manager]);

  // Guards against an out-of-order response overwriting a newer one when the
  // reader changes preset twice before the first resolves.
  const generation = useRef(0);

  const load = useCallback(async (next: CalibrationRequest) => {
    const mine = ++generation.current;
    try {
      const source = await manager.resolve(next);
      const cal = await source.calibrate(next);
      const [curve, lambda, geology] = await Promise.all([
        source.series(cal, 400),
        source.lambdaHistory(cal, 400),
        source.geologicColumn(cal),
      ]);
      if (mine !== generation.current) return;
      setCalibration(cal);
      setSeries(curve);
      setHistory(lambda);
      setColumn(geology);
      setError(null);
    } catch (caught) {
      if (mine !== generation.current) return;
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, [manager]);

  // Overrides are part of what gets solved, so they belong in the request the
  // loader sees rather than in a second channel.
  const effectiveRequest = useMemo<CalibrationRequest>(
    () => (overridden.size ? { ...request, overrides } : request),
    [request, overrides, overridden.size],
  );

  useEffect(() => { void load(effectiveRequest); }, [load, effectiveRequest]);

  // Changing preset abandons any overrides: they were values for a different
  // calibration, and carrying them across would silently mix two scenarios.
  const changePreset = useCallback((patch: Partial<CalibrationRequest>) => {
    setOverrides({});
    setRequest((r) => ({ ...r, ...patch }));
  }, []);

  const onParameter = useCallback((name: string, value: number) => {
    setOverrides((o) => ({ ...o, [name]: value }));
  }, []);

  const sourceKind = state.kind;

  return (
    <div className="app">
      <header className="app-header">
        <h1>CARD — accelerated radiometric decay</h1>
        <p>
          Converting between young-earth ages and the apparent ages rock would
          yield under a time-varying decay rate. The Flood begins at the
          Precambrian–Cambrian contact and ends a year later at the boundary you
          choose. The rate falls steeply across that year and far more slowly
          for millennia after, so it takes three matched dates — those two
          contacts and the end of the Ice Age — to fix the curve exactly.
        </p>
      </header>

      <div className="layout">
        <div>
          <PresetPicker
            data={data}
            chronology={request.chronology}
            boundary={request.boundary}
            onChronology={(chronology) => changePreset({ chronology })}
            onBoundary={(boundary) => changePreset({ boundary })}
          />

          {calibration ? (
            <CalibrationReadout
              calibration={calibration}
              sourceKind={sourceKind}
              lambdaF2={
                data.presets[`${request.chronology}:${request.boundary}`]
                  ?.lambda_F2
              }
            />
          ) : null}

          {modeSchema && calibration ? (
            <ParameterPanel
              mode={modeSchema}
              fittable={precomputed.fittable}
              values={calibration.params}
              overridden={overridden}
              onChange={onParameter}
              onReset={() => setOverrides({})}
              // Honest about the cost before it is incurred, rather than
              // freezing on a 5.8 MB fetch the reader did not ask for.
              willStartDownload={sourceKind !== "live"}
            />
          ) : null}

          <section className="panel" aria-labelledby="source-heading">
            <h2 id="source-heading">Model source</h2>
            <p style={{ margin: "0 0 .6rem", fontSize: ".84rem", color: "var(--text-secondary)" }}>
              {sourceKind === "live" ? (
                <>Running the <strong>card</strong> Python package in your
                browser. Every value is computed, not interpolated.</>
              ) : (
                <>Reading precomputed results. The full model is a 5.8&nbsp;MB
                download and is not fetched unless you ask for it.</>
              )}
            </p>
            <span className={`badge ${sourceKind === "live" ? "live" : ""}`}>
              {sourceKind === "live" ? "live · exact" : "precomputed · ≈1%"}
            </span>
            {sourceKind !== "live" ? (
              <p style={{ margin: ".7rem 0 0" }}>
                <button
                  className="action"
                  disabled={state.liveStatus === "booting"}
                  onClick={() => void manager.ensureLive().then(
                    () => load(request),
                    () => undefined,
                  )}
                >
                  {state.liveStatus === "booting"
                    ? "Loading the model…"
                    : "Load the full model (5.8 MB)"}
                </button>
              </p>
            ) : null}
            {state.liveStatus === "failed" ? (
              <p className="notice" style={{ marginTop: ".7rem", marginBottom: 0 }}>
                <strong>Could not load the full model.</strong> {state.error}{" "}
                Presets still work.
              </p>
            ) : null}
          </section>
        </div>

        <main>
          {error ? (
            <p className="notice"><strong>Error.</strong> {error}</p>
          ) : null}

          {series && calibration ? (
            <>
              <div
                className="segmented"
                role="group"
                aria-label="Age chart orientation"
              >
                <button
                  type="button"
                  className={orientation === "apparent" ? "on" : ""}
                  aria-pressed={orientation === "apparent"}
                  onClick={() => setOrientation("apparent")}
                >
                  True → apparent
                </button>
                <button
                  type="button"
                  className={orientation === "true" ? "on" : ""}
                  aria-pressed={orientation === "true"}
                  onClick={() => setOrientation("true")}
                >
                  Apparent → true
                </button>
              </div>
              <AgeComparisonChart
                series={series}
                calibration={calibration}
                orientation={orientation}
              />
            </>
          ) : null}

          {history ? (
            <LambdaHistoryChart
              history={history}
              zoom={lambdaZoom}
              onZoom={setLambdaZoom}
            />
          ) : null}

          {column && calibration ? (
            <GeologicColumnChart
              column={column}
              calibration={calibration}
              fullColumnBoundary={fullColumnBoundary}
              onSelectBoundary={(boundary) =>
                setRequest((r) => ({ ...r, boundary }))}
            />
          ) : null}

          {series && calibration ? (
            <SeriesTable series={series} calibration={calibration} />
          ) : null}
        </main>
      </div>
    </div>
  );
}
