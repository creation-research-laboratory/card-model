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
import { diskBodyLoader } from "../model/testData.js";
import type { Calibration, GeologicColumn } from "../model/types.js";

const WEB = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const data = JSON.parse(
  readFileSync(join(WEB, "public", "precomputed.json"), "utf8"),
) as PrecomputedData;

const source = new PrecomputedSource(data, diskBodyLoader);

let container: HTMLDivElement;
let root: Root;
let calibration: Calibration;
let column: GeologicColumn;

beforeEach(async () => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  calibration = await source.calibrate({
    chronology: "masoretic", boundary: "kpg", iceAge: "default", mode: "flood_only",
  });
  column = await source.geologicColumn(calibration);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function render(props: Partial<Parameters<typeof GeologicColumnChart>[0]> = {}) {
  act(() => {
    root.render(
      <StrictMode>
        <GeologicColumnChart
          column={column} calibration={calibration} {...props}
        />
      </StrictMode>,
    );
  });
}

/** Row labels that drew a real bar, in chart order. */
const barred = () =>
  [...container.querySelectorAll<SVGGElement>("svg g > g")]
    .filter((g) => g.querySelector('rect[fill*="series"]'))
    .map((g) => g.querySelector("text")?.textContent ?? "");

/** Row labels replaced by a note instead of a bar, with the note. */
const noted = () =>
  [...container.querySelectorAll<SVGGElement>("svg g > g")]
    .filter((g) => !g.querySelector("rect") && g.querySelectorAll("text").length === 2)
    .map((g) => [...g.querySelectorAll("text")].map((t) => t.textContent).join(": "));

/** The marker groups, which are the only `<g>` carrying a help cursor. */
const markerGroups = () =>
  [...container.querySelectorAll<SVGGElement>('g[style*="help"]')];

const labelOf = (g: SVGGElement) => g.querySelector("text")?.textContent ?? "";
/** Every line of a marker's label stack, joined. */
const labelsOf = (g: SVGGElement) =>
  [...g.querySelectorAll("text")].map((t) => t.textContent).join(" | ");
const detail = () =>
  container.querySelector(".marker-detail")?.textContent?.replace(/\s+/g, " ").trim() ?? "";

describe("what is drawn", () => {
  it("draws one mark for the Flood and one for the Ice Age", () => {
    render();
    expect(markerGroups().map(labelOf))
      .toEqual(["Flood (1 yr)", "End of the Ice Age"]);
  });

  it("names the chosen boundary on the band itself", () => {
    // The reason the marker layer exists at all: t_F2 is the contact the
    // reader picked, so the figure has to show that the exponential hands
    // over at K/Pg rather than at some anonymous "end of the Flood".
    render();
    expect(labelsOf(markerGroups()[0])).toContain("K/Pg");
    expect(labelsOf(markerGroups()[0])).toContain("Precambrian-Cambrian");
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

  it("names the contact beside the role in the detail", () => {
    render();
    act(() => {
      markerGroups()[0].dispatchEvent(
        new PointerEvent("pointerover", { bubbles: true }),
      );
    });
    expect(detail()).toContain("Flood ends — Cretaceous-Paleogene (K/Pg)");
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

describe("the Flood-year view", () => {
  it("spreads out the units the full axis cannot resolve", () => {
    // For the K/Pg calibration everything from the Cambrian to the Cretaceous
    // sits between t_F2 and t_F — one year in six thousand. On the full axis
    // those bars are sub-pixel and floored to the 2px minimum, so they carry
    // no width information at all; the Flood view is what makes them readable.
    render({ zoom: "full" });
    const wideInFull = [...container.querySelectorAll<SVGRectElement>('rect[fill*="series"]')]
      .filter((r) => Number(r.getAttribute("width")) > 3).length;

    render({ zoom: "flood" });
    const wideInFlood = [...container.querySelectorAll<SVGRectElement>('rect[fill*="series"]')]
      .filter((r) => Number(r.getAttribute("width")) > 3).length;

    expect(wideInFlood).toBeGreaterThan(wideInFull);
  });

  it("says where a unit went instead of drawing it at the frame edge", () => {
    // Clamping alone would collapse a post-Flood unit to zero width against
    // the right edge, then widen it to the 2px minimum — a mark exactly where
    // the unit is not.
    render({ zoom: "flood" });
    const notes = noted().join(" ");
    expect(notes).toContain("Holocene: after the Flood year");
    expect(barred()).not.toContain("Holocene");
  });

  it("keeps the Flood's own units drawn", () => {
    render({ zoom: "flood" });
    for (const unit of ["Cambrian", "Jurassic", "Cretaceous"]) {
      expect(barred()).toContain(unit);
    }
  });

  it("separates t_F and t_F2 once the axis can resolve a year", () => {
    // In the full view they collapse into one band; here there is room for
    // two, so the K/Pg handover finally gets a mark of its own.
    render({ zoom: "full" });
    expect(markerGroups()).toHaveLength(2);       // Flood band + Ice Age

    render({ zoom: "flood" });
    const labels = markerGroups().map(labelOf);
    expect(labels).toContain("Flood begins");
    expect(labels).toContain("Flood ends");
    // And the Ice Age is millennia away, so it is off this axis entirely.
    expect(labels.join(" ")).not.toContain("Ice Age");
  });

  it("labels the axis finely enough to tell 4399 from 4400", () => {
    // "4.4 kyr" is the same string for both ends of the Flood year, which
    // would make the zoomed axis meaningless.
    render({ zoom: "flood" });
    const ticks = [...container.querySelectorAll("text")]
      .map((t) => t.textContent ?? "")
      .filter((t) => /^43\d\d(\.\d+)?$/.test(t));
    expect(new Set(ticks).size).toBeGreaterThan(1);
  });

  it("offers the toggle only when it can be acted on", () => {
    render({ zoom: "full", onZoom: () => {} });
    expect(container.textContent).toContain("The Flood year");
    render({ zoom: "full" });
    expect(container.textContent).not.toContain("The Flood year");
  });
});

describe("the Flood-day marks", () => {
  it("appear only in the Flood view", () => {
    // On the full axis the Flood year is 0.13 px, so they would be swallowed
    // by its band and add two names to its hover text for no visible mark.
    render({ zoom: "full" });
    expect(markerGroups().map(labelOf).join(" ")).not.toMatch(/40 days/);

    render({ zoom: "flood" });
    const labels = markerGroups().map(labelOf);
    expect(labels).toContain("40 days");
    expect(labels).toContain("150 days");
  });

  it("are dotted, so they read as neither a breakpoint nor an anchor", () => {
    render({ zoom: "flood" });
    const byLabel = new Map(markerGroups().map((g) => [labelOf(g), g]));
    const dash = (l: string) =>
      byLabel.get(l)!.querySelector("line")!.getAttribute("stroke-dasharray");
    expect(dash("Flood begins")).toBeNull();   // solid — lambda jumps
    expect(dash("40 days")).toBe("1 3");       // dotted — model does nothing
    expect(dash("150 days")).toBe("1 3");
  });

  it("sit between the systems the model puts either side of them", () => {
    // The point of showing them: 40 days lands mid-Palaeozoic and 150 days
    // inside the Cretaceous, so a reader can see which systems the model
    // deposits while the rain fell and which while the waters prevailed.
    render({ zoom: "flood" });
    const xOf = (label: string) => {
      const g = markerGroups().find((m) => labelOf(m) === label)!;
      return Number(g.querySelector("line")!.getAttribute("x1"));
    };
    expect(xOf("Flood begins")).toBeLessThan(xOf("40 days"));
    expect(xOf("40 days")).toBeLessThan(xOf("150 days"));
    expect(xOf("150 days")).toBeLessThan(xOf("Flood ends"));
  });

  it("says outright that the model has no feature there", () => {
    render({ zoom: "flood" });
    const g = markerGroups().find((m) => labelOf(m) === "150 days")!;
    act(() => {
      g.dispatchEvent(new PointerEvent("pointerover", { bubbles: true }));
    });
    expect(detail()).toMatch(/model has no feature here/);
    expect(detail()).toMatch(/Gen\. 7:24/);
  });

  it("names the third key in the legend only where it is used", () => {
    render({ zoom: "flood" });
    expect(container.textContent).toMatch(/day of the Flood account/);
    render({ zoom: "full" });
    expect(container.textContent).not.toMatch(/day of the Flood account/);
  });
});

describe("labels do not overwrite each other", () => {
  /** y of a marker group's first label line. */
  const labelY = (label: string) => {
    const g = markerGroups().find((m) => labelOf(m) === label)!;
    return Number(g.querySelector("text")!.getAttribute("y"));
  };

  it("drops a colliding stack to a second tier", () => {
    // "Precambrian-Cambrian" is ~110px anchored at the Flood's start and the
    // 40-day mark is ~59px away, so on one tier the contact name runs straight
    // through its neighbour.
    render({ zoom: "flood" });
    expect(labelY("40 days")).not.toBe(labelY("Flood begins"));
  });

  it("keeps well-separated marks on the same tier", () => {
    // Staggering everything would be as bad as staggering nothing — the tier
    // has to mean "this one would have collided".
    render({ zoom: "flood" });
    expect(labelY("Flood begins")).toBe(labelY("Flood ends"));
  });

  it("leaves the full view on one tier, where the calendar sits", () => {
    render({ zoom: "full" });
    const ys = markerGroups().map((g) =>
      Number(g.querySelector("text")!.getAttribute("y")));
    expect(new Set(ys).size).toBe(1);
  });
});
