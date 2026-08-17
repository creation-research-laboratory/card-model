/**
 * The marker layer, rendered.
 *
 * `breakpoints.test.ts` checks that the right instants are identified and
 * classified; this checks that what reaches the screen matches — a solid rule
 * where the model changes, a dashed one where it was merely fitted, and the
 * Flood's two breakpoints drawn as one band because a year is a third of a
 * pixel at this scale.
 *
 * @vitest-environment happy-dom
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { StrictMode, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { GeologicColumnChart } from "./GeologicColumnChart.js";
import { PrecomputedSource, type PrecomputedData } from "../model/PrecomputedSource.js";
import type { Calibration, GeologicColumn } from "../model/types.js";

const WEB = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const data = JSON.parse(
  readFileSync(join(WEB, "public", "precomputed.json"), "utf8"),
) as PrecomputedData;

const source = new PrecomputedSource(data);

let container: HTMLDivElement;
let root: Root;
let calibration: Calibration;
let column: GeologicColumn;

beforeEach(async () => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  calibration = await source.calibrate({
    chronology: "masoretic", boundary: "kpg", mode: "flood_only",
  });
  column = await source.geologicColumn(calibration);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function render() {
  act(() => {
    root.render(
      <StrictMode>
        <GeologicColumnChart column={column} calibration={calibration} />
      </StrictMode>,
    );
  });
}

/** The marker groups, which are the only `<g>` carrying a help cursor. */
const markerGroups = () =>
  [...container.querySelectorAll<SVGGElement>('g[style*="help"]')];

const labelOf = (g: SVGGElement) => g.querySelector("text")?.textContent ?? "";
const detail = () =>
  container.querySelector(".marker-detail")?.textContent?.replace(/\s+/g, " ").trim() ?? "";

describe("what is drawn", () => {
  it("draws one mark for the Flood and one for the Ice Age", () => {
    render();
    expect(markerGroups().map(labelOf)).toEqual(["Flood (1 yr)", "Ice Age ends"]);
  });

  it("collapses t_F and t_F2 into a single band, labelled with the real span", () => {
    // One year is ~0.13 px here. Two separate lines would render as one visible
    // mark while implying two were drawn, so they become a band — and the
    // label, not the width, carries the duration.
    render();
    const flood = markerGroups()[0];
    const band = [...flood.querySelectorAll("rect")]
      .find((r) => r.getAttribute("fill") !== "transparent");
    expect(band).toBeDefined();
    expect(Number(band!.getAttribute("width"))).toBeGreaterThanOrEqual(3);
    expect(labelOf(flood)).toContain("1 yr");
  });

  it("distinguishes a rate change from a fitted date by line style", () => {
    render();
    const [flood, ice] = markerGroups();
    // Solid: something changes here.
    expect(flood.querySelector("line")!.getAttribute("stroke-dasharray")).toBeNull();
    // Dashed: the curve was pinned here, but lambda does not change.
    expect(ice.querySelector("line")!.getAttribute("stroke-dasharray")).toBe("4 3");
  });

  it("gives the Ice Age no band, because it is an instant not an interval", () => {
    render();
    const bands = [...markerGroups()[1].querySelectorAll("rect")]
      .filter((r) => r.getAttribute("fill") !== "transparent");
    expect(bands).toHaveLength(0);
  });
});

describe("the detail strip", () => {
  it("shows the legend until something is hovered", () => {
    render();
    expect(detail()).toMatch(/where λ or its relaxation constant changes/);
  });

  it("explains both Flood breakpoints when the band is hovered", () => {
    render();
    act(() => {
      markerGroups()[0].dispatchEvent(
        new PointerEvent("pointerover", { bubbles: true }),
      );
    });
    const text = detail();
    expect(text).toContain("Flood begins");
    expect(text).toContain("Flood ends");
    // The distinction that matters: lambda jumps at one and not the other.
    expect(text).toMatch(/discontinuous/);
    expect(text).toMatch(/continuous here/);
    expect(text).toMatch(/k_PF/);
  });

  it("says plainly that the Ice Age is not a rate change", () => {
    render();
    act(() => {
      markerGroups()[1].dispatchEvent(
        new PointerEvent("pointerover", { bubbles: true }),
      );
    });
    expect(detail()).toMatch(/not a rate change/i);
  });

  it("returns to the legend once the pointer leaves", () => {
    render();
    const flood = markerGroups()[0];
    act(() => {
      flood.dispatchEvent(new PointerEvent("pointerover", { bubbles: true }));
    });
    expect(detail()).toContain("Flood begins");
    act(() => {
      flood.dispatchEvent(new PointerEvent("pointerout", { bubbles: true }));
    });
    expect(detail()).toMatch(/where λ or its relaxation constant changes/);
  });
});
