/**
 * Loading the precomputed layer from disk, for tests.
 *
 * The index no longer carries the curves — seventy presets hold 3.8 MB between
 * them, and the index is awaited before the first paint — so a test that wants
 * a preset's arrays has to read its file too. This does what the browser's
 * `fetch` loader does, from the filesystem.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  PrecomputedSource, bodyFileName,
  type BodyLoader, type PrecomputedData, type PresetBody,
} from "./PrecomputedSource.js";

const WEB = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const PUBLIC = join(WEB, "public");

export const precomputedData = JSON.parse(
  readFileSync(join(PUBLIC, "precomputed.json"), "utf8"),
) as PrecomputedData;

/** Reads `public/presets/<key>.json`, as the browser fetches it. */
export const diskBodyLoader: BodyLoader = async (key) =>
  JSON.parse(
    readFileSync(join(PUBLIC, "presets", bodyFileName(key)), "utf8"),
  ) as PresetBody;

/** Synchronous form, for assertions about the stored arrays themselves. */
export function bodyOf(key: string): PresetBody {
  return JSON.parse(
    readFileSync(join(PUBLIC, "presets", bodyFileName(key)), "utf8"),
  ) as PresetBody;
}

/** Index + everything a preset needs, as one object. */
export function presetWithBody(key: string) {
  return { ...precomputedData.presets[key], ...bodyOf(key) };
}

export function makeSource(data: PrecomputedData = precomputedData) {
  return new PrecomputedSource(data, diskBodyLoader);
}

/** The shipped default request, with every dimension filled in. */
export const defaultRequest = {
  chronology: precomputedData.defaults.chronology,
  boundary: precomputedData.defaults.boundary,
  iceAge: precomputedData.defaults.ice_age,
  mode: precomputedData.defaults.mode,
};
