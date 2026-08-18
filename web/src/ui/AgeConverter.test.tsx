/**
 * The converter is a debounced async round trip with two editable fields, which
 * is exactly the shape that produces subtle bugs: answers landing out of order,
 * a field overwritten mid-keystroke, an error left on screen after it stops
 * being true.
 *
 * The model itself is stubbed here — the live suite already checks that
 * `forward_age` and `inverse_age` agree with Python. What is under test is the
 * component's own behaviour around them.
 *
 * @vitest-environment happy-dom
 */

import { StrictMode, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgeConverter } from "./AgeConverter.js";
import { ModelError } from "../model/types.js";

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
  vi.useRealTimers();
});

/** A stand-in for the model: apparent age is 1000x the true age. */
const forward = vi.fn(async (trueAge: number) => trueAge * 1000);
const inverse = vi.fn(async (secularAge: number) => secularAge / 1000);

function render(props: Partial<Parameters<typeof AgeConverter>[0]> = {}) {
  act(() => {
    root.render(
      <StrictMode>
        <AgeConverter
          forward={forward}
          inverse={inverse}
          exact
          initialApparent={66_000_000}
          debounceMs={50}
          {...props}
        />
      </StrictMode>,
    );
  });
}

const fields = () => [...container.querySelectorAll<HTMLInputElement>('input[type="text"]')];
const [APPARENT, TRUE] = [0, 1];

function type(index: number, text: string) {
  const input = fields()[index];
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype, "value",
  )!.set!;
  act(() => {
    setter.call(input, text);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function settle(ms = 120) {
  await act(async () => { await new Promise((r) => setTimeout(r, ms)); });
}

describe("converting", () => {
  beforeEach(() => { forward.mockClear(); inverse.mockClear(); });

  it("goes apparent → true", async () => {
    render();
    type(APPARENT, "5000000");
    await settle();
    expect(inverse).toHaveBeenCalledWith(5_000_000);
    expect(fields()[TRUE].value).toMatch(/5.*kyr/);
  });

  it("goes true → apparent", async () => {
    render();
    type(TRUE, "4400");
    await settle();
    expect(forward).toHaveBeenCalledWith(4400);
    expect(fields()[APPARENT].value).toMatch(/4\.4.*Myr/);
  });

  it("does not overwrite the field being typed in", async () => {
    // The round trip is async; without one authoritative side, the answer
    // computed from one box lands in the other and clobbers what is being
    // typed.
    render();
    type(TRUE, "4400");
    await settle();
    expect(fields()[TRUE].value).toBe("4400");
  });

  it("accepts scientific notation and thousands separators", async () => {
    render();
    type(APPARENT, "66e6");
    await settle();
    expect(inverse).toHaveBeenCalledWith(66_000_000);

    inverse.mockClear();
    type(APPARENT, "2,580,000");
    await settle();
    expect(inverse).toHaveBeenCalledWith(2_580_000);
  });

  it("debounces rather than converting per keystroke", async () => {
    vi.useFakeTimers();
    render();
    for (const text of ["6", "66", "660", "6600"]) type(APPARENT, text);
    expect(inverse).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(80); });
    expect(inverse).toHaveBeenCalledTimes(1);
    expect(inverse).toHaveBeenCalledWith(6600);
  });
});

describe("does not chase its own tail", () => {
  beforeEach(() => { forward.mockClear(); inverse.mockClear(); });

  it("converts once per edit, not once per answer", async () => {
    // The first version held the two fields as peers, so the effect depended
    // on the derived one and writing an answer scheduled another conversion.
    // It settled, but only after a second round trip — ~1.6 s rather than
    // ~200 ms, with every intermediate answer rendered on the way.
    render();
    type(APPARENT, "66e6");
    await settle(400);
    expect(inverse).toHaveBeenCalledTimes(1);
  });

  it("settles within one debounce of the last keystroke", async () => {
    render({ debounceMs: 50 });
    type(TRUE, "2556");
    await settle(150);
    expect(fields()[APPARENT].value).toMatch(/^2\.556 Myr$/);
  });
});

describe("what it says when it cannot answer", () => {
  beforeEach(() => { forward.mockClear(); inverse.mockClear(); });

  it("shows the package's own prose for an out-of-domain age", async () => {
    // Not our wording. The package explains the domain — and names the oldest
    // apparent age it can produce — better than the UI could.
    const message =
      "secular_age (1e+30) exceeds the maximum this model can produce " +
      "(5.36539e+08, for a rock formed on Day 1 of Creation).";
    render({ inverse: vi.fn(async () => { throw new ModelError(message); }) });
    type(APPARENT, "1e30");
    await settle();
    expect(container.textContent).toContain(message);
    expect(fields()[TRUE].value).toBe("");
  });

  it("flags text that is not a number without calling the model", async () => {
    render();
    type(APPARENT, "sixty six million");
    await settle();
    expect(inverse).not.toHaveBeenCalled();
    expect(container.textContent).toMatch(/is not a number/);
  });

  it("clears the error once the input becomes answerable again", async () => {
    render();
    type(APPARENT, "nonsense");
    await settle();
    expect(container.textContent).toMatch(/is not a number/);

    type(APPARENT, "66e6");
    await settle();
    expect(container.textContent).not.toMatch(/is not a number/);
  });

  it("leaves an emptied field genuinely empty, not marked", async () => {
    // "≈ " on its own reads as an answer of approximately nothing.
    render({ exact: false });
    type(APPARENT, "66e6");
    await settle();
    expect(fields()[TRUE].value).toMatch(/^≈ /);

    type(APPARENT, "");
    await settle();
    expect(fields()[TRUE].value).toBe("");
  });

  it("empties the other field rather than leaving a stale answer", async () => {
    render();
    type(APPARENT, "66e6");
    await settle();
    expect(fields()[TRUE].value).not.toBe("");

    type(APPARENT, "");
    await settle();
    expect(fields()[TRUE].value).toBe("");
  });
});

describe("honesty about precision", () => {
  it("marks derived values and says so when interpolating", async () => {
    render({ exact: false });
    type(APPARENT, "66e6");
    await settle();
    expect(fields()[TRUE].value).toMatch(/^≈/);
    expect(container.textContent).toMatch(/Interpolated/);
  });

  it("claims nothing extra when the model computed it", async () => {
    render({ exact: true });
    type(APPARENT, "66e6");
    await settle();
    expect(fields()[TRUE].value).not.toMatch(/≈/);
    expect(container.textContent).toMatch(/Computed by the model/);
  });

  it("re-converts when the calibration behind it changes", async () => {
    // Moving a slider must update the answer without the reader retyping.
    render();
    type(APPARENT, "66e6");
    await settle();
    expect(fields()[TRUE].value).toMatch(/66.*kyr/);

    const tenfold = vi.fn(async (s: number) => s / 100);
    render({ inverse: tenfold });
    await settle();
    expect(tenfold).toHaveBeenCalledWith(66_000_000);
  });
});
