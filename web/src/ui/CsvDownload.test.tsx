/**
 * The download panel.
 *
 * Nothing here checks the CSV's contents — `tests/test_series.py` owns that,
 * and the live suite pins the bytes against the CLI. What is under test is
 * the component's own behaviour: that it names the file after the model that
 * produced it, that a failure is reported rather than swallowed, and that the
 * blob URL is released.
 *
 * @vitest-environment happy-dom
 */

import { StrictMode, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CsvDownload } from "./CsvDownload.js";
import type { Calibration } from "../model/types.js";

let container: HTMLDivElement;
let root: Root;
let clicked: HTMLAnchorElement[];
let revoked: string[];

const calibration = {
  request: { chronology: "masoretic", boundary: "kpg", mode: "flood_only" },
  presetKey: "masoretic:kpg:default",
} as unknown as Calibration;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);

  clicked = [];
  revoked = [];
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: () => "blob:fake",
    revokeObjectURL: (u: string) => revoked.push(u),
  });
  // happy-dom does not navigate on anchor.click(); record instead.
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicked.push(this);
  });
});

afterEach(async () => {
  // The component revokes its blob URL on a zero-delay timer, so a click in
  // one test can still have a callback in flight when the next test replaces
  // `revoked` — and it then lands in the new array. Draining here keeps each
  // test's recording its own.
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function render(props: Partial<Parameters<typeof CsvDownload>[0]> = {}) {
  act(() => {
    root.render(
      <StrictMode>
        <CsvDownload
          calibration={calibration}
          onDownload={async () => "a,b\n1,2\n"}
          willStartDownload={false}
          {...props}
        />
      </StrictMode>,
    );
  });
}

const button = () =>
  [...container.querySelectorAll("button")].find((b) => /Download|Preparing/.test(b.textContent ?? ""))!;

async function press() {
  await act(async () => { button().click(); });
}

describe("downloading", () => {
  it("asks for the selected number of rows", async () => {
    const onDownload = vi.fn(async () => "csv");
    render({ onDownload });
    const select = container.querySelector("select")!;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLSelectElement.prototype, "value",
      )!.set!;
      setter.call(select, "20000");
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await press();
    expect(onDownload).toHaveBeenCalledWith(20000);
  });

  it("names the file after the model that produced it", async () => {
    render();
    await press();
    expect(clicked).toHaveLength(1);
    expect(clicked[0].download).toBe("card-masoretic-kpg-2000rows.csv");
  });

  it("marks a file built from overridden parameters as custom", async () => {
    // Otherwise two files with the same name would describe different models
    // — the trap the provenance header exists to close.
    const custom = { ...calibration, presetKey: undefined } as Calibration;
    render({ calibration: custom });
    await press();
    expect(clicked[0].download).toContain("custom");
  });

  it("releases the blob URL", async () => {
    // 20,000 rows is ~1.5 MB held until revoked.
    vi.useFakeTimers();
    try {
      render();
      await act(async () => { button().click(); });
      await act(async () => { await vi.advanceTimersByTimeAsync(10); });
      expect(revoked).toEqual(["blob:fake"]);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("when it cannot", () => {
  it("reports the failure instead of silently doing nothing", async () => {
    render({ onDownload: async () => { throw new Error("Pyodide is offline"); } });
    await press();
    expect(container.textContent).toContain("Pyodide is offline");
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
    expect(clicked).toHaveLength(0);
  });

  it("recovers for a second attempt", async () => {
    let fail = true;
    render({
      onDownload: async () => {
        if (fail) { fail = false; throw new Error("boom"); }
        return "csv";
      },
    });
    await press();
    expect(container.textContent).toContain("boom");
    await press();
    expect(container.textContent).not.toContain("boom");
    expect(clicked).toHaveLength(1);
  });

  it("warns about the model download before incurring it", async () => {
    render({ willStartDownload: true });
    expect(container.textContent).toMatch(/5\.8\s*MB download/);
    render({ willStartDownload: false });
    expect(container.textContent).not.toMatch(/5\.8\s*MB download/);
  });
});
