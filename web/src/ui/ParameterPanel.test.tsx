/**
 * The panel must render whatever the package says is free — never a list of
 * its own.
 *
 * That property is the whole reason for running real `card` in the browser
 * instead of porting it, and it is the kind of thing that decays quietly: one
 * hardcoded `["lambda_F", "k_F"]` and the app silently stops tracking the
 * model. So it is asserted against **both** modes, including the `general` one
 * that ships authored but disabled — an unexercised expansion path is a claim,
 * not a capability.
 *
 * @vitest-environment happy-dom
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { StrictMode, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ParameterPanel, type ModeSchema } from "./ParameterPanel.js";
import type { PrecomputedData } from "../model/PrecomputedSource.js";
import type { GeneralParams } from "../model/types.js";

const WEB = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const data = JSON.parse(
  readFileSync(join(WEB, "public", "precomputed.json"), "utf8"),
) as PrecomputedData;

const FITTABLE = (data.modes["$fittable"] as string[]);
const VALUES = data.presets["masoretic:kpg"].params as GeneralParams;

function modeSchema(mode: string, chronology = "masoretic"): ModeSchema {
  const entry = data.modes[mode];
  if (!entry || Array.isArray(entry)) throw new Error(`no mode ${mode}`);
  return entry.by_chronology[chronology] as ModeSchema;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function render(mode: ModeSchema, props: Partial<Parameters<typeof ParameterPanel>[0]> = {}) {
  act(() => {
    root.render(
      <StrictMode>
        <ParameterPanel
          mode={mode}
          fittable={FITTABLE}
          values={VALUES}
          overridden={new Set()}
          onChange={() => {}}
          onReset={() => {}}
          willStartDownload={false}
          {...props}
        />
      </StrictMode>,
    );
  });
  return container;
}

const sliderIds = () =>
  [...container.querySelectorAll<HTMLInputElement>('input[type="range"]')]
    .map((i) => i.id.replace(/^p-/, ""));

describe("renders exactly what the package says is free", () => {
  for (const mode of ["flood_only", "general"]) {
    it(`${mode}: one control per fittable free name`, () => {
      const schema = modeSchema(mode);
      const expected = schema.free.filter((n) => FITTABLE.includes(n));
      render(schema);

      expect(sliderIds()).toEqual(expected);
      expect(expected.length).toBeGreaterThan(0);
    });
  }

  it("the general mode really does offer more than flood_only", () => {
    // Otherwise the test above could pass with both modes accidentally equal,
    // and the expansion path would be untested while looking tested.
    const floodOnly = modeSchema("flood_only").free.filter((n) => FITTABLE.includes(n));
    const general = modeSchema("general").free.filter((n) => FITTABLE.includes(n));
    expect(general.length).toBeGreaterThan(floodOnly.length);
    for (const name of floodOnly) expect(general).toContain(name);
    // Specifically, the Creation-week parameters.
    expect(general).toContain("lambda_c");
    expect(general).toContain("k_c");
  });

  it("skips lambda_bg structurally, not by name", () => {
    // Its spec has minimum == maximum, so `is_fittable` is false. It is in
    // `free` for both modes; a panel that filtered by name instead would break
    // the moment another parameter became degenerate.
    const schema = modeSchema("flood_only");
    expect(schema.free).toContain("lambda_bg");
    expect(FITTABLE).not.toContain("lambda_bg");
    render(schema);
    expect(sliderIds()).not.toContain("lambda_bg");
  });
});

describe("reads the spec rather than assuming", () => {
  it("takes log or linear from x-log-scale, not from the parameter's name", () => {
    // k_F is a rate like k_PF but is declared linear: over a one-year Flood its
    // range is a few multiples of 1/year and its default of 0 has no log10.
    const props = modeSchema("flood_only").schema.properties;
    expect(props.k_PF["x-log-scale"]).toBe(true);
    expect(props.k_F["x-log-scale"]).toBe(false);
  });

  it("can represent the calibrated value of every control it draws", () => {
    // A slider clamped below its own preset would show the wrong answer on
    // load. This caught lambda_F sitting above a stale 1e9 bound.
    const schema = modeSchema("flood_only");
    for (const name of schema.free.filter((n) => FITTABLE.includes(n))) {
      const prop = schema.schema.properties[name];
      const value = (VALUES as unknown as Record<string, number>)[name];
      expect(value).toBeGreaterThanOrEqual(prop.minimum);
      expect(value).toBeLessThanOrEqual(prop.maximum);
    }
  });

  it("follows the chronology for date bounds", () => {
    expect(modeSchema("general", "masoretic").schema.properties.t_c.maximum)
      .toBe(data.chronologies.masoretic.age_of_earth);
    expect(modeSchema("general", "septuagint").schema.properties.t_c.maximum)
      .toBe(data.chronologies.septuagint.age_of_earth);
  });
});

describe("interaction", () => {
  it("debounces, so a dragged slider does not solve once per frame", async () => {
    vi.useFakeTimers();
    try {
      const onChange = vi.fn();
      const schema = modeSchema("flood_only");
      render(schema, { onChange, debounceMs: 100 });

      const slider = container.querySelector<HTMLInputElement>("#p-lambda_F")!;
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype, "value",
      )!.set!;

      for (const v of ["0.50", "0.55", "0.60", "0.65"]) {
        act(() => {
          setter.call(slider, v);
          slider.dispatchEvent(new Event("input", { bubbles: true }));
        });
      }
      expect(onChange).not.toHaveBeenCalled();

      await act(async () => { await vi.advanceTimersByTimeAsync(150); });
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange.mock.calls[0][0]).toBe("lambda_F");
    } finally {
      vi.useRealTimers();
    }
  });

  it("warns about the download before it is incurred", () => {
    render(modeSchema("flood_only"), { willStartDownload: true });
    expect(container.textContent).toMatch(/5\.8\s*MB download/);
    render(modeSchema("flood_only"), { willStartDownload: false });
    expect(container.textContent).not.toMatch(/MB download/);
  });

  it("shows the package's rejection verbatim, next to the controls", () => {
    // Real prose from `GeneralModelParams.__post_init__`. It explains *why* the
    // rule exists, which is the whole reason for showing it rather than a
    // generic "invalid input" — so the test pins the explanation, not just the
    // first clause.
    const message =
      "t_F (1656.0) precedes t_c (3000.0).  The DATEs must be ordered " +
      "t_c <= t_F <= t_F2.";
    render(modeSchema("general"), { error: message });
    expect(container.textContent).toContain(message);
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
  });

  it("says nothing when the model accepted the values", () => {
    render(modeSchema("general"), { error: null });
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.textContent).not.toMatch(/rejected/i);
  });

  it("keeps the controls usable while rejected, so the reader can back out", () => {
    // Disabling them on error would strand the reader at the invalid value
    // with no way to return.
    render(modeSchema("general"), { error: "t_F (1656.0) precedes t_c (3000.0)." });
    const sliders = [...container.querySelectorAll<HTMLInputElement>('input[type="range"]')];
    expect(sliders.length).toBeGreaterThan(0);
    expect(sliders.every((s) => !s.disabled)).toBe(true);
  });

  it("offers a reset only once something has been overridden", () => {
    render(modeSchema("flood_only"), { overridden: new Set() });
    expect(container.textContent).not.toMatch(/Reset/);
    render(modeSchema("flood_only"), { overridden: new Set(["lambda_F"]) });
    expect(container.textContent).toMatch(/Reset/);
  });
});
