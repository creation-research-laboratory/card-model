/**
 * Controls for the model's free parameters, generated from the package.
 *
 * **This file contains no list of parameters.** It renders whatever
 * `free` names the package returned, reading each control's range, units,
 * scale and tooltip from the `ParamSpec` declared on the dataclass field. Add a
 * parameter to `GeneralModelParams` and a control appears here with no change
 * to this file — that property is the reason for running real `card` in the
 * browser rather than porting it, so it is worth protecting.
 *
 * Two consequences of taking the schema seriously:
 *
 *   * `lambda_bg` is in `free` but not in `fittable`, because its spec has
 *     `minimum == maximum`. It is skipped structurally, not by name.
 *   * `k_F` is linear where the other rates are logarithmic, because its spec
 *     says `x-log-scale: false` — over a one-year Flood its range is a few
 *     multiples of 1/year and its default of 0 has no log10.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import type { GeneralParams } from "../model/types.js";
import { formatMultiplier, trim } from "../charts/format.js";
import { usePowerUser } from "./preferences.js";

/** One property of the JSON Schema the package emits. */
export interface ParamProperty {
  title: string;
  description: string;
  default: number;
  minimum: number;
  maximum: number;
  "x-unit": string;
  "x-log-scale": boolean;
  "x-is-date": boolean;
}

export interface ModeSchema {
  schema: { properties: Record<string, ParamProperty> };
  free: string[];
  fixed: Record<string, number>;
}

interface Props {
  mode: ModeSchema;
  /** Names the package considers free to vary at all (`is_fittable`). */
  fittable: string[];
  /** Current values, from the calibration in force. */
  values: GeneralParams;
  /** Names the reader has overridden, so they can be shown as modified. */
  overridden: ReadonlySet<string>;
  /** Fires at most every `debounceMs`; the reader drags faster than we solve. */
  onChange(name: string, value: number): void;
  onReset(): void;
  /** True when acting on a change would start the 5.8 MB download. */
  willStartDownload: boolean;
  /**
   * The package's own words when it rejected this combination, shown verbatim
   * beside the controls that caused it.
   *
   * Each slider is bounded by its own spec, so a single parameter cannot leave
   * its range. What no bound can prevent is a rule *between* parameters — the
   * DATEs must satisfy `t_c <= t_F <= t_F2`, and two independently draggable
   * date sliders can violate that at any time. `GeneralModelParams` explains
   * such a failure better than a generic "invalid input" ever could, so its
   * message is passed through untouched.
   */
  error?: string | null;
  disabled?: boolean;
  debounceMs?: number;
}

/**
 * Map a value to a 0–1 slider position and back.
 *
 * Log-scale parameters span up to eleven decades; a linear slider over that
 * range would spend 90% of its travel above 1e10. The rates have a minimum of
 * exactly 0, which has no logarithm, so those get a small floor rather than a
 * special case at every call site.
 */
function scaleFor(prop: ParamProperty) {
  if (!prop["x-log-scale"]) {
    const span = prop.maximum - prop.minimum || 1;
    return {
      toSlider: (v: number) => (v - prop.minimum) / span,
      fromSlider: (t: number) => prop.minimum + t * span,
    };
  }
  const lo = Math.max(prop.minimum, 1e-12);
  const hi = Math.max(prop.maximum, lo * 10);
  const logLo = Math.log10(lo);
  const logHi = Math.log10(hi);
  return {
    toSlider: (v: number) =>
      (Math.log10(Math.min(Math.max(v, lo), hi)) - logLo) / (logHi - logLo),
    fromSlider: (t: number) => 10 ** (logLo + t * (logHi - logLo)),
  };
}

function display(name: string, value: number, prop: ParamProperty): string {
  if (prop["x-is-date"]) return trim(value, 6);
  return prop["x-log-scale"] ? formatMultiplier(value) : trim(value, 6);
}

export function ParameterPanel({
  mode, fittable, values, overridden, onChange, onReset,
  willStartDownload, error, disabled, debounceMs = 100,
}: Props) {
  const powerUser = usePowerUser();
  // Only the names the package returned, and only those it considers free to
  // vary. Never a literal list.
  const names = useMemo(
    () => mode.free.filter((n) => fittable.includes(n)),
    [mode.free, fittable],
  );

  // Local echo so a dragged slider tracks the pointer at full frame rate while
  // the solve behind it runs at most every `debounceMs`.
  const [draft, setDraft] = useState<Record<string, number>>({});
  useEffect(() => setDraft({}), [values]);

  const [pending, setPending] = useState<Record<string, number>>({});
  useEffect(() => {
    if (Object.keys(pending).length === 0) return;
    const timer = setTimeout(() => {
      for (const [name, value] of Object.entries(pending)) onChange(name, value);
      setPending({});
    }, debounceMs);
    return () => clearTimeout(timer);
  }, [pending, onChange, debounceMs]);

  const set = useCallback((name: string, value: number) => {
    setDraft((d) => ({ ...d, [name]: value }));
    setPending((p) => ({ ...p, [name]: value }));
  }, []);

  const valueOf = (name: string) =>
    draft[name] ?? (values as unknown as Record<string, number>)[name];

  return (
    <section className="panel" aria-labelledby="parameters-heading">
      <h2 id="parameters-heading">Parameters</h2>

      {error ? (
        <p className="notice" role="alert" style={{ marginTop: 0 }}>
          <strong>The model rejected these values.</strong>{" "}
          <span className="converter-error">{error}</span>
        </p>
      ) : null}

      {willStartDownload ? (
        <p className="notice" style={{ marginTop: 0 }}>
          Changing any of these needs the full model, a{" "}
          <strong>5.8&nbsp;MB download</strong>. It starts when you move a
          control, and only has to happen once.
        </p>
      ) : null}

      {names.map((name) => {
        const prop = mode.schema.properties[name];
        if (!prop) return null;
        const scale = scaleFor(prop);
        const value = valueOf(name);
        const isOverridden = overridden.has(name);

        return (
          <div className="param" key={name}>
            <label className="param-label" htmlFor={`p-${name}`}>
              <span title={prop.description}>
                {name}
                {prop["x-unit"] ? (
                  <span className="param-unit"> {prop["x-unit"]}</span>
                ) : null}
                {prop["x-log-scale"] ? (
                  <span className="param-unit" title="logarithmic slider">
                    {" "}· log
                  </span>
                ) : null}
              </span>
              <output className={isOverridden ? "changed" : ""}>
                {display(name, value, prop)}
              </output>
            </label>
            <input
              id={`p-${name}`}
              type="range"
              min={0}
              max={1}
              step={0.0005}
              disabled={disabled}
              value={scale.toSlider(value)}
              aria-describedby={`d-${name}`}
              onChange={(e) => set(name, scale.fromSlider(Number(e.target.value)))}
            />
            {/*
              * Hidden, not removed. `aria-describedby` points here, and a
              * reader who wants a denser view has not asked to be told less
              * about what a parameter means — the label's `title` still shows
              * it on hover, and assistive technology still reads it.
              */}
            <p
              id={`d-${name}`}
              className={powerUser ? "visually-hidden" : "param-help"}
            >
              {prop.description}
            </p>
          </div>
        );
      })}

      {mode.fixed && Object.keys(mode.fixed).length ? (
        <details className="table-view" style={{ marginTop: ".6rem" }}>
          <summary>
            Held fixed by this mode ({Object.keys(mode.fixed).length})
          </summary>
          <dl className="readout" style={{ marginTop: ".4rem" }}>
            {Object.entries(mode.fixed).map(([name, v]) => (
              <div key={name} style={{ display: "contents" }}>
                <dt>{name}</dt>
                <dd>{trim(v, 6)}</dd>
              </div>
            ))}
          </dl>
        </details>
      ) : null}

      {overridden.size > 0 ? (
        <p style={{ margin: ".7rem 0 0" }}>
          <button className="action" onClick={onReset} disabled={disabled}>
            Reset to the calibrated values
          </button>
        </p>
      ) : null}
    </section>
  );
}
