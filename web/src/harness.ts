/**
 * Developer harness for the Phase 3 model layer.
 *
 * Phase 3 has no app UI. This page exists to exercise the layer in a real
 * browser, which the headless tests cannot do: they use `DirectTransport` in
 * Node, so the actual Worker path — `pyodide.worker.ts` plus `WorkerTransport`
 * — is otherwise never executed.
 *
 * It also gives the Phase 2 boot stall somewhere to reproduce. That failure
 * only appeared in a browser with a page being loaded repeatedly, and until now
 * there has been no page.
 *
 * Phase 4 replaces this with the actual app.
 */

import { ModelSourceManager } from "./model/ModelSourceManager.js";
import { PrecomputedSource, type PrecomputedData } from "./model/PrecomputedSource.js";
import { PyodideSource } from "./model/PyodideSource.js";
import { WorkerTransport } from "./worker/transport.js";
import type { CalibrationRequest } from "./model/types.js";

const $ = (id: string) => document.getElementById(id)!;
const fmt = (n: number, d = 2) => Number(n).toFixed(d);

function rows(el: HTMLElement, pairs: Array<[string, string, string?]>) {
  el.innerHTML = pairs
    .map(([k, v, cls = ""]) => `<tr><td class="k">${k}</td><td class="v ${cls}">${v}</td></tr>`)
    .join("");
}

function log(message: string, cls = "") {
  const line = document.createElement("div");
  line.className = cls;
  line.textContent = `${new Date().toISOString().slice(11, 23)}  ${message}`;
  $("log").prepend(line);
}

const t0 = performance.now();

// ---------------------------------------------------------------- first paint
const data = (await (await fetch(`${import.meta.env.BASE_URL}precomputed.json`)).json()) as PrecomputedData;
const precomputed = new PrecomputedSource(data);
const firstPaintMs = performance.now() - t0;

const manager = new ModelSourceManager({
  precomputed,
  createLive: async () => {
    const worker = new Worker(new URL("./worker/pyodide.worker.ts", import.meta.url), {
      type: "module",
      name: "card-pyodide",
    });
    return new PyodideSource(
      // Assets live at the site root, not next to the worker module.
      new WorkerTransport(worker, new URL(import.meta.env.BASE_URL, location.href).href),
      {
        chronologies: data.chronologies,
        boundaries: data.boundaries,
        secondConstraint: data.second_constraint,
      },
    );
  },
});

// A Pyodide instance holds ~100 MB. Terminating on pagehide is what makes
// repeated reloads deterministic — see the Phase 2 stall notes.
addEventListener("pagehide", () => void manager.dispose());

let request: CalibrationRequest = {
  chronology: data.defaults.chronology,
  boundary: data.defaults.boundary,
  mode: data.defaults.mode,
};

// ------------------------------------------------------------------- controls
const chronSelect = $("chronology") as HTMLSelectElement;
const boundSelect = $("boundary") as HTMLSelectElement;
chronSelect.innerHTML = Object.entries(data.chronologies)
  .map(([k, c]) => `<option value="${k}">${c.label}${c.provisional ? " (provisional)" : ""}</option>`)
  .join("");
boundSelect.innerHTML = Object.entries(data.boundaries)
  .map(([k, b]) => `<option value="${k}">${b.label}</option>`)
  .join("");
chronSelect.value = request.chronology;
boundSelect.value = request.boundary;

const lambdaInput = $("lambda_F") as HTMLInputElement;
const converterInput = $("secular") as HTMLInputElement;

manager.subscribe((state) => {
  $("source").textContent = state.kind;
  $("source").className = state.kind === "live" ? "ok" : "warn";
  $("liveStatus").textContent = state.liveStatus + (state.error ? ` — ${state.error}` : "");
  if (state.liveStatus === "ready") log("live source ready — swapped", "ok");
  if (state.liveStatus === "booting") log("booting Pyodide in a worker…");
  if (state.liveStatus === "failed") log(`boot failed: ${state.error}`, "bad");
});

async function refresh() {
  const started = performance.now();
  const source = await manager.resolve(request);
  const cal = await source.calibrate(request);
  const series = await source.series(cal, 400);
  const elapsed = performance.now() - started;

  const approx = cal.exact ? "" : "≈ ";
  rows($("result"), [
    ["source", `${source.kind}${cal.exact ? " (exact)" : " (interpolated)"}`,
     cal.exact ? "ok" : "warn"],
    ["lambda_F", `${cal.params.lambda_F.toPrecision(9)}`],
    ["k_F (in-Flood)", `${cal.params.k_F.toPrecision(9)}`],
    ["k_PF (post-Flood)", `${cal.params.k_PF.toPrecision(9)}`],
    ["lambda_c / k_c", `${cal.params.lambda_c} / ${cal.params.k_c}`],
    ["max |residual|", cal.maxAbsResidual.toExponential(2)],
    ["max secular age", `${approx}${cal.maxSecularAge.toPrecision(6)} yr`],
    ["series points", String(series.trueAge.length)],
    ["round trip", `${fmt(elapsed)} ms`],
  ]);

  rows($("constraints"), cal.constraints.map((c) => [
    c.label,
    `${c.trueAge} YBP → ${c.secularAge.toExponential(3)} yr apparent`,
  ]));

  await convert();
}

async function convert() {
  const secular = Number(converterInput.value);
  if (!Number.isFinite(secular) || secular <= 0) return;
  try {
    const source = await manager.resolve(request);
    const cal = await source.calibrate(request);
    const trueAge = await source.inverseAge(cal, secular);
    const back = await source.forwardAge(cal, trueAge);
    const approx = cal.exact ? "" : "≈ ";
    rows($("converter"), [
      ["secular age in", `${secular.toExponential(4)} yr`],
      ["true age out", `${approx}${fmt(trueAge, 3)} YBP`, cal.exact ? "ok" : "warn"],
      ["round trip back", `${approx}${back.toExponential(6)} yr`],
      ["digits you may quote", cal.exact ? "all of them" : "~3 (0.03% inverse error)"],
    ]);
  } catch (error) {
    rows($("converter"), [["error", String((error as Error).message), "bad"]]);
  }
}

// ------------------------------------------------------------------ listeners
chronSelect.onchange = () => {
  request = { ...request, chronology: chronSelect.value, overrides: undefined };
  lambdaInput.value = "";
  log(`preset → ${chronSelect.value}:${boundSelect.value}`);
  void refresh();
};
boundSelect.onchange = () => {
  request = { ...request, boundary: boundSelect.value, overrides: undefined };
  lambdaInput.value = "";
  log(`preset → ${chronSelect.value}:${boundSelect.value}`);
  void refresh();
};

// This is the gesture that boots Pyodide: a custom parameter is exactly what
// the precomputed table cannot answer.
lambdaInput.oninput = () => {
  const value = Number(lambdaInput.value);
  if (!lambdaInput.value.trim()) {
    request = { ...request, overrides: undefined };
    void refresh();
    return;
  }
  if (!Number.isFinite(value)) return;
  request = { ...request, overrides: { lambda_F: value } };
  if (manager.needsLive(request)) {
    log("custom parameter — precomputed layer cannot answer, booting live", "warn");
  }
  void refresh();
};
converterInput.oninput = () => void convert();

$("bootNow").addEventListener("click", () => {
  void manager.ensureLive().then(
    () => refresh(),
    (error) => log(`boot failed: ${error.message}`, "bad"),
  );
});

$("compare").addEventListener("click", async () => {
  const live = await manager.ensureLive();
  const preRequest: CalibrationRequest = {
    chronology: chronSelect.value, boundary: boundSelect.value, mode: "flood_only",
  };
  const liveCal = await live.calibrate(preRequest);
  const preCal = await precomputed.calibrate(preRequest);

  const probes = [10, 100, 1000, 2556, 4400, 6000].filter(
    (a) => a <= liveCal.chronology.ageOfEarth,
  );
  const out: Array<[string, string, string?]> = [];
  let worstSpot = 0;
  for (const age of probes) {
    const exact = await live.forwardAge(liveCal, age);
    const approx = await precomputed.forwardAge(preCal, age);
    const rel = Math.abs(approx / exact - 1);
    worstSpot = Math.max(worstSpot, rel);
    out.push([`${age} YBP`,
      `exact ${exact.toExponential(6)} · approx ${approx.toExponential(6)} · ${(rel * 100).toFixed(4)}%`]);
  }

  // Round ages mostly land on grid rows — two of them are calibration anchors,
  // exact by construction — so the spot checks above flatter the table. The
  // honest figure is the worst case at grid midpoints, which is what the "≈"
  // in the UI is promising.
  const series = await precomputed.series(preCal);
  let worst = 0;
  for (let i = 0; i < series.trueAge.length - 1; i += 3) {
    const x = Math.sqrt(Math.max(series.trueAge[i], 1e-9) * series.trueAge[i + 1]);
    if (!(x > 0 && x <= liveCal.chronology.ageOfEarth)) continue;
    const exact = await live.forwardAge(liveCal, x);
    if (exact <= 0) continue;
    worst = Math.max(worst, Math.abs((await precomputed.forwardAge(preCal, x)) / exact - 1));
  }
  out.push(["worst at these spot checks", `${(worstSpot * 100).toFixed(4)}%`]);
  out.push(["<b>worst at grid midpoints</b>",
    `<b>${(worst * 100).toFixed(4)}%</b> — the number the "≈" promises`,
    worst < 5e-3 ? "ok" : "bad"]);
  rows($("compareOut"), out);
  log(`compared precomputed vs live: worst ${(worst * 100).toFixed(4)}%`,
      worst < 5e-3 ? "ok" : "bad");
});

// -------------------------------------------------------------------- startup
rows($("boot"), [
  ["first paint (precomputed loaded)", `${fmt(firstPaintMs)} ms`, "ok"],
  ["generated by", `card ${precomputed.generatedBy.card_version}`],
  ["presets available", String(precomputed.presetKeys.length)],
  ["Pyodide", "not started — that is the point", "warn"],
]);
log("precomputed layer ready; Pyodide deliberately not started");
await refresh();
