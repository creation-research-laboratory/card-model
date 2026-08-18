/**
 * The preference has to survive a reload and, more importantly, has to fail
 * quietly. `localStorage` throws outright when a browser is set to block site
 * data, and a display preference is not worth a blank page.
 *
 * @vitest-environment happy-dom
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { STORAGE_KEY, readPreferences, writePreferences } from "./preferences.js";

afterEach(() => {
  vi.unstubAllGlobals();
  try { localStorage.clear(); } catch { /* nothing to clear */ }
});

/** Replace `localStorage` with one that throws the way a blocked browser does. */
function blockStorage(on: "get" | "set" | "both") {
  vi.stubGlobal("localStorage", {
    getItem: () => {
      if (on === "get" || on === "both") throw new DOMException("blocked");
      return null;
    },
    setItem: () => {
      if (on === "set" || on === "both") throw new DOMException("blocked");
    },
    removeItem: () => {},
    clear: () => {},
  });
}

describe("round trip", () => {
  it("defaults to off when nothing is stored", () => {
    expect(readPreferences().powerUser).toBe(false);
  });

  it("restores what was written", () => {
    writePreferences({ powerUser: true });
    expect(readPreferences().powerUser).toBe(true);
    writePreferences({ powerUser: false });
    expect(readPreferences().powerUser).toBe(false);
  });

  it("stores under a versioned key", () => {
    // So a later preference with a different shape need not interpret this one.
    writePreferences({ powerUser: true });
    expect(localStorage.getItem(STORAGE_KEY)).toBeTruthy();
    expect(STORAGE_KEY).toMatch(/\.v\d+$/);
  });
});

describe("bad input is a default, not a crash", () => {
  it("survives unparseable JSON", () => {
    localStorage.setItem(STORAGE_KEY, "{not json");
    expect(() => readPreferences()).not.toThrow();
    expect(readPreferences().powerUser).toBe(false);
  });

  it("survives a value of the wrong shape", () => {
    for (const junk of ['"a string"', "42", "null", "[]"]) {
      localStorage.setItem(STORAGE_KEY, junk);
      expect(readPreferences().powerUser).toBe(false);
    }
  });

  it("does not take a truthy non-boolean for true", () => {
    // A future build storing "true" or 1 must not silently mean enabled.
    for (const junk of ['{"powerUser":"true"}', '{"powerUser":1}']) {
      localStorage.setItem(STORAGE_KEY, junk);
      expect(readPreferences().powerUser).toBe(false);
    }
  });

  it("ignores keys it does not know", () => {
    localStorage.setItem(STORAGE_KEY, '{"powerUser":true,"somethingElse":9}');
    expect(readPreferences()).toEqual({ powerUser: true });
  });
});

describe("storage that refuses to work", () => {
  it("reads a default when getItem throws", () => {
    blockStorage("get");
    expect(() => readPreferences()).not.toThrow();
    expect(readPreferences().powerUser).toBe(false);
  });

  it("swallows a refused write", () => {
    // The choice then lasts the session rather than taking the page down.
    blockStorage("set");
    expect(() => writePreferences({ powerUser: true })).not.toThrow();
  });

  it("copes with localStorage missing entirely", () => {
    vi.stubGlobal("localStorage", undefined);
    expect(readPreferences().powerUser).toBe(false);
    expect(() => writePreferences({ powerUser: true })).not.toThrow();
  });
});
