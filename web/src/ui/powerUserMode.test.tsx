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
import { diskBodyLoader } from "../model/testData.js";
import type { Calibration, GeneralParams } from "../model/types.js";

const WEB = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const data = JSON.parse(
  readFileSync(join(WEB, "public", "precomputed.json"), "utf8"),
) as PrecomputedData;
const source = new PrecomputedSource(data, diskBodyLoader);

const FITTABLE = data.modes["$fittable"] as string[];
const VALUES = data.presets["masoretic:kpg:default"].params as GeneralParams;
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
    chronology: "masoretic", boundary: "kpg", iceAge: "default", mode: "flood_only",
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
        iceAge="default"
        onChronology={() => {}} onBoundary={() => {}} onIceAge={() => {}}
      />
    );
    mount(picker, false);
    expect(container.textContent).toMatch(/rate spikes there/);
    mount(picker, true);
    expect(container.textContent).not.toMatch(/rate spikes there/);
    // The selects are the point of the panel and must survive: chronology,
    // post-Flood boundary, Ice Age.
    expect(container.querySelectorAll("select")).toHaveLength(3);
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

  it("drops the download notice, which the source panel duplicates", () => {
    // The size is on the button that performs the download — "Load the full
    // model (5.8 MB)" — so this paragraph is duplication in a dense view, not
    // a warning the reader would otherwise miss.
    mount(panel({ willStartDownload: true }), false);
    expect(container.textContent).toMatch(/5\.8\s*MB download/);
    mount(panel({ willStartDownload: true }), true);
    expect(container.textContent).not.toMatch(/5\.8\s*MB download/);
  });

  it("keeps the provisional-chronology warning", () => {
    // A caveat about the data's trustworthiness. Hiding it to save two lines
    // would be trading correctness for density.
    const picker = (
      <PresetPicker
        data={data} chronology="septuagint" boundary="kpg"
        iceAge="default"
        onChronology={() => {}} onBoundary={() => {}} onIceAge={() => {}}
      />
    );
    mount(picker, true);
    expect(container.textContent).toMatch(/Provisional values/i);
  });

  it("drops the interpolation paragraph but keeps the ≈ on the values", () => {
    // The marking is what tells a reader *which* numbers are approximate, and
    // it is per-value — so it stays in every mode. The paragraph explaining it
    // does not: the source badge already reads "precomputed · ≈1%".
    const readout = (
      <CalibrationReadout calibration={calibration} sourceKind="precomputed" />
    );
    mount(readout, false);
    expect(container.querySelector(".notice")).not.toBeNull();

    mount(readout, true);
    expect(container.querySelector(".notice")).toBeNull();
    expect(container.textContent).toContain("≈");
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

describe("preset help belongs to the control it describes", () => {
  const picker = (chronology = "masoretic") => (
    <PresetPicker
      data={data} chronology={chronology} boundary="kpg" iceAge="default"
      onChronology={() => {}} onBoundary={() => {}} onIceAge={() => {}}
    />
  );

  /** The help each select points at, via aria-describedby. */
  const helpFor = (id: string) => {
    const select = container.querySelector<HTMLSelectElement>(`#${id}`)!;
    const described = select.getAttribute("aria-describedby")!;
    return container.querySelector(`#${described}`)!;
  };

  it("gives every select its own description", () => {
    // The defect this fixes: one paragraph sat under the *last* select and
    // said "this choice", meaning the one two controls above it.
    mount(picker(), false);
    for (const id of ["preset-chronology", "preset-boundary", "preset-ice-age"]) {
      expect(helpFor(id).textContent).toBeTruthy();
    }
  });

  it("describes the boundary select in terms of the boundary", () => {
    mount(picker(), false);
    const text = helpFor("preset-boundary").textContent ?? "";
    expect(text).toMatch(/ends/);
    expect(text).not.toMatch(/Ice Age/);
  });

  it("describes the Ice Age select in terms of the Ice Age", () => {
    mount(picker(), false);
    const text = helpFor("preset-ice-age").textContent ?? "";
    expect(text).toMatch(/relaxes|millennia/);
    // And no longer explains the control above it.
    expect(text).not.toMatch(/a year later|fallen to/);
  });

  it("puts each help after the select it describes", () => {
    // Position is the whole complaint: text before its control reads as
    // belonging to the previous one.
    mount(picker(), false);
    for (const id of ["preset-chronology", "preset-boundary", "preset-ice-age"]) {
      const select = container.querySelector(`#${id}`)!;
      const help = helpFor(id);
      expect(select.compareDocumentPosition(help))
        .toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    }
  });

  it("hides all of it in power-user mode, without breaking the association", () => {
    mount(picker(), true);
    expect(container.querySelector(".field-help")).toBeNull();
    // Still described, still readable by assistive technology.
    for (const id of ["preset-chronology", "preset-boundary", "preset-ice-age"]) {
      expect(helpFor(id).className).toBe("visually-hidden");
      expect(helpFor(id).textContent).toBeTruthy();
    }
  });

  it("keeps the provisional warning in power-user mode", () => {
    mount(picker("septuagint"), true);
    expect(container.textContent).toMatch(/Provisional values/i);
  });
});
