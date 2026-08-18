/**
 * What power-user mode is allowed to remove.
 *
 * The mode has one rule, and it is the only thing here worth protecting: it
 * hides *explanation*. It must never hide a warning, an error, a unit, or a
 * precision caveat — a reader who asked for a denser view has not asked to be
 * told less about what the numbers mean, or to stop being warned.
 *
 * These render through the real `PreferencesProvider` with `localStorage`
 * pre-set, so each case also exercises the persistence path end to end.
 *
 * @vitest-environment happy-dom
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { StrictMode, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { CalibrationReadout } from "./CalibrationReadout.js";
import { ParameterPanel, type ModeSchema } from "./ParameterPanel.js";
import { PresetPicker } from "./PresetPicker.js";
import { PreferencesProvider, STORAGE_KEY } from "./preferences.js";
import { PrecomputedSource, type PrecomputedData } from "../model/PrecomputedSource.js";
import type { Calibration, GeneralParams } from "../model/types.js";

const WEB = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const data = JSON.parse(
  readFileSync(join(WEB, "public", "precomputed.json"), "utf8"),
) as PrecomputedData;
const source = new PrecomputedSource(data);

const FITTABLE = data.modes["$fittable"] as string[];
const VALUES = data.presets["masoretic:kpg"].params as GeneralParams;
const schema = (data.modes.flood_only as { by_chronology: Record<string, unknown> })
  .by_chronology.masoretic as ModeSchema;

let container: HTMLDivElement;
let root: Root;
let calibration: Calibration;

beforeEach(async () => {
  localStorage.clear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  calibration = await source.calibrate({
    chronology: "masoretic", boundary: "kpg", mode: "flood_only",
  });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  localStorage.clear();
});

/**
 * Mount `node` with the preference pre-set, the way a returning reader is.
 *
 * A *fresh* root each time. The provider reads storage in a `useState`
 * initialiser — which is the point, it is what makes the first paint correct —
 * so re-rendering an existing root would keep the old value and quietly test
 * nothing.
 */
function mount(node: React.ReactNode, powerUser: boolean) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ powerUser }));
  act(() => root.unmount());
  root = createRoot(container);
  act(() => {
    root.render(
      <StrictMode>
        <PreferencesProvider>{node}</PreferencesProvider>
      </StrictMode>,
    );
  });
  return container;
}

const panel = (props: Partial<Parameters<typeof ParameterPanel>[0]> = {}) => (
  <ParameterPanel
    mode={schema} fittable={FITTABLE} values={VALUES}
    overridden={new Set()} onChange={() => {}} onReset={() => {}}
    willStartDownload={false} {...props}
  />
);

describe("it removes explanation", () => {
  it("drops the per-parameter descriptions from view", () => {
    mount(panel(), false);
    expect(container.querySelector(".param-help")).not.toBeNull();
    mount(panel(), true);
    expect(container.querySelector(".param-help")).toBeNull();
  });

  it("drops the preset explanation but keeps the controls", () => {
    const picker = (
      <PresetPicker
        data={data} chronology="masoretic" boundary="kpg"
        onChronology={() => {}} onBoundary={() => {}}
      />
    );
    mount(picker, false);
    expect(container.textContent).toMatch(/rate spikes there/);
    mount(picker, true);
    expect(container.textContent).not.toMatch(/rate spikes there/);
    // The selects are the point of the panel and must survive.
    expect(container.querySelectorAll("select")).toHaveLength(2);
  });
});

describe("it never removes what the reader is owed", () => {
  it("keeps a rejected-parameter error", () => {
    const message = "t_F (1656.0) precedes t_c (3000.0).  The DATEs must be "
      + "ordered t_c <= t_F <= t_F2.";
    mount(panel({ error: message }), true);
    expect(container.textContent).toContain(message);
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
  });

  it("keeps the download warning", () => {
    mount(panel({ willStartDownload: true }), true);
    expect(container.textContent).toMatch(/5\.8\s*MB download/);
  });

  it("keeps the provisional-chronology warning", () => {
    // A caveat about the data's trustworthiness. Hiding it to save two lines
    // would be trading correctness for density.
    const picker = (
      <PresetPicker
        data={data} chronology="septuagint" boundary="kpg"
        onChronology={() => {}} onBoundary={() => {}}
      />
    );
    mount(picker, true);
    expect(container.textContent).toMatch(/Provisional values/i);
  });

  it("keeps the interpolation caveat, shortened", () => {
    const readout = (
      <CalibrationReadout calibration={calibration} sourceKind="precomputed" />
    );
    mount(readout, true);
    // The numbers a reader would cite survive; the teaching around them goes.
    expect(container.textContent).toMatch(/0\.8%/);
    expect(container.textContent).toMatch(/0\.9%/);
    expect(container.textContent).not.toMatch(/the solver produced them/);
  });

  it("keeps units and values on every control", () => {
    mount(panel(), true);
    expect(container.querySelectorAll('input[type="range"]').length)
      .toBe(schema.free.filter((n) => FITTABLE.includes(n)).length);
    expect(container.querySelectorAll("output").length).toBeGreaterThan(0);
  });

  it("keeps the parameter description reachable, not deleted", () => {
    // `aria-describedby` points at it, so removing the node would strip the
    // description from the accessibility tree rather than merely from view.
    mount(panel(), true);
    const slider = container.querySelector<HTMLInputElement>("#p-lambda_F")!;
    const describedBy = slider.getAttribute("aria-describedby")!;
    const description = container.querySelector(`#${describedBy}`);
    expect(description).not.toBeNull();
    expect(description!.textContent).toMatch(/Decay rate during the Flood/);
    expect(description!.className).toBe("visually-hidden");
  });
});

describe("the choice survives a reload", () => {
  it("comes back on when storage says so", () => {
    mount(panel(), true);
    expect(container.querySelector(".param-help")).toBeNull();

    // A fresh provider, as a new page load would build.
    act(() => root.unmount());
    root = createRoot(container);
    act(() => {
      root.render(<PreferencesProvider>{panel()}</PreferencesProvider>);
    });
    expect(container.querySelector(".param-help")).toBeNull();
  });

  it("marks the document so the stylesheet can follow", () => {
    mount(panel(), true);
    expect(document.documentElement.dataset.power).toBe("on");
    mount(panel(), false);
    expect(document.documentElement.dataset.power).toBe("off");
  });
});
