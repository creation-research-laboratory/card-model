/**
 * Entry point.
 *
 * Loads the precomputed layer before the first render, so the app paints with
 * a chart already on screen rather than an empty frame. It is ~39 kB gzipped —
 * a fetch, not a download.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./ui/App.js";
import type { PrecomputedData } from "./model/PrecomputedSource.js";
import "./ui/theme.css";

const response = await fetch(`${import.meta.env.BASE_URL}precomputed.json`);
if (!response.ok) {
  throw new Error(`could not load precomputed.json: ${response.status}`);
}
const data = (await response.json()) as PrecomputedData;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App data={data} />
  </StrictMode>,
);
