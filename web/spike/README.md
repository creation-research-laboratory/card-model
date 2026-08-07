# Phase 2 — Pyodide go/no-go spike

Boots Pyodide in a Web Worker, installs the `card` wheel built from this repo,
and runs the real `solve_flood_only`. No UI, no charts: the question is whether
running the actual Python package in a browser is viable, and at what cost.

**Verdict: GO, with one design consequence — see [Cold start](#cold-start-is-the-real-cost).**

## Running it

```bash
cd web/spike
npm install
node vendor-pyodide.mjs                     # copy the runtime out of node_modules
python -m build --wheel --outdir vendor ../..  # build the card wheel
node serve.mjs                              # http://localhost:8422
```

`node measure.mjs 6` runs the same boot sequence headlessly N times and reports
a distribution — use that for timings, and the browser page for payload and for
proving it works in a browser at all.

`THROTTLE_KBPS=500 NO_STORE=1 node serve.mjs` serves slowly, for cold-start
measurement. The throttle is crude (it meters 16 kB chunks through
`setTimeout`, whose clamping makes the delivered rate well below the nominal
one), which is why the page reports **measured effective throughput** rather
than quoting the setting.

## What it proves

**The stdlib-only work holds up in a real browser.** `numpy_loaded: false`,
`scipy_loaded: false`, reported by the interpreter itself after a full solve.
The whole premise of shipping `card` to a browser depended on this.

**The browser agrees with the interpreter.** `lambda_F = 318753.882`,
`k_F = 0.00482991111`, max |residual| `8.88e-16` — matching the values pinned
from the Python package to better than 1e-5.

**A wheel needs no installer.** A wheel is a zip and the model path is pure
Python, so `sys.path.insert(0, "/card_model-...whl")` *is* the installation —
median **2.8 ms**. micropip would work but adds its own wheel and a dependency
resolver with nothing to resolve.

**Steady-state compute is a non-issue.** Median `solve_flood_only` **8.2 ms**
headless / **6.0 ms** in the browser worker, and a 400-point series — what a
chart redraw actually costs — **1.8 ms**. Against a 16.7 ms frame budget, live
recalculation behind a dragged slider is comfortable.

| | headless (Node, 6/6 runs) | browser worker |
| --- | --- | --- |
| total boot | median **1539 ms** (1461–1757) | 2.0–3.1 s |
| of which `loadPyodide` | median 1499 ms | 1.8–1.9 s |
| wheel install | 2.8 ms | 5.0 ms |
| steady `solve_flood_only` | 8.2 ms | 6.0 ms |
| 400-point series | 1.8 ms | 1.4 ms |

## Cold start is the real cost

Payload is **5.84 MB over the wire** (12.97 MB decoded), measured from the
worker's own Resource Timing — the main thread cannot see these fetches, and
measuring from there reports a fictitious ~0 MB.

| file | over the wire | decoded |
| --- | --- | --- |
| `pyodide.asm.wasm` | 3.09 MB | 9.15 MB |
| `python_stdlib.zip` | 2.43 MB | 2.43 MB |
| `pyodide.asm.mjs` | 0.23 MB | 1.19 MB |
| **`card` wheel** | **0.06 MB** | 0.06 MB |
| `pyodide-lock.json` | 0.02 MB | 0.11 MB |

The package we actually wrote is **1%** of the download. This confirms the
plan's 5.82 MB estimate almost exactly, and confirms that the numpy + scipy
removal was the difference between viable and not — those two wheels would have
added 16.1 MB to the 5.84 MB above.

Throttled, at a **measured 142 kB/s** (~1.1 Mbps, between Chrome's Slow and
Fast 3G presets), the network was busy for **42.1 s** and boot took 42.2 s.
Boot is essentially all download. Scaling the fixed 5.84 MB payload:

| connection | download | + ~1.5 s init |
| --- | --- | --- |
| 1.1 Mbps *(measured)* | 42 s | 43 s |
| 4 Mbps | ~12 s | ~13 s |
| 10 Mbps | ~4.8 s | ~6 s |
| 25 Mbps | ~1.9 s | ~3 s |
| repeat visit (cached) | — | ~1.5–3 s |

**This is why the plan's precomputed first-paint layer is load-bearing rather
than a nicety.** A first-time visitor on anything short of good broadband
cannot be shown a spinner for this long. The design that survives the
measurement is:

1. paint the default preset instantly from a small precomputed JSON (~40 kB);
2. **do not** boot Pyodide on page load — start it when the user first touches
   a parameter control, or after the page has been idle and visible for a
   moment;
3. swap the `ModelSource` when it is ready.

The plan listed lazy-load as a fallback if boot was slow. It should be the
default.

## Known issue: repeated boots in one browser session

During automated testing, roughly half the page loads stalled inside
`loadPyodide` — after the wasm was fully fetched (server logs confirm), with
the promise neither resolving nor rejecting, and no console error. A fresh
browser process always worked; repeated boots in a long-lived one often did
not. Main-thread heap was 1.2 MB at the time and the machine had 32 GB, so this
is not ordinary memory exhaustion.

Headless Node ran **6/6** with the identical sequence, and the browser
succeeded on every *first* load, so this does not block Phase 3. But it is
unexplained, and it should be re-tested deliberately in Phase 3 once the worker
is long-lived and the page is not being reloaded in a loop — including whether
`worker.terminate()` on `pagehide` (added here) is sufficient. If it recurs
with real users, it is a go/no-go issue in its own right.

Two smaller traps, both fixed here, both of which produced quietly wrong
measurements first:

- The page's `performance.getEntriesByType("resource")` does not see
  worker-initiated fetches. Payload must be collected inside the worker.
- `serve.mjs` cached compressed bodies by path alone, so editing a file
  mid-session served the stale copy — the measurement then described code that
  was no longer on disk. It now keys on size too.

## Files

| | |
| --- | --- |
| `index.html` | measurement harness and results table |
| `worker.mjs` | boots Pyodide, zipimports the wheel, exposes an RPC |
| `bridge.py` | the Python side of the worker boundary — deliberately thin |
| `measure.mjs` | headless N-run timing harness |
| `serve.mjs` | static server: correct MIME types, brotli/gzip, optional throttle |
| `vendor-pyodide.mjs` | copies the runtime out of `node_modules` |

`bridge.py` is a real `.py` file rather than a string inside the worker so it
is lintable, diffable, and importable from pytest. Everything of substance
lives in `card`; the bridge only converts dicts to package calls and back.
