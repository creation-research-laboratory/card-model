# CARD web frontend — architecture and implementation plan

Status: **proposal, for review.** Nothing here is built yet.

Goal: a static web app under `web/` (structurally independent, so it can split
into its own repo later) that (1) visualizes model output for **user-supplied
inputs**, (2) ships preset input bundles (LXX vs Masoretic chronology; K/Pg vs
Neogene/Quaternary boundary), and (3) exports a calibrated time series as CSV.

Free parameter entry is a core use case, which rules out a
precompute-only app. Keeping the logic in the Python core rules out a port.

---

## 1. Decision

**Run the real `card` package in the browser under Pyodide, in a Web Worker,
after making the model path stdlib-only.**

No port, no backend, no duplicated math, still fully static, still deployable
to GitHub Pages. The frontend imports `card.models` and `card.calibrate` and
calls them directly — the same functions the CLI and the paper call.

The enabling move is that **`card`'s scalar path doesn't actually need numpy or
scipy**, and removing that dependency cuts the download by 74%.

## 2. Evidence

Everything below is measured, not estimated.

### numpy is being used as a scalar math library

Across `models.py` the entire numpy surface is `np.exp`, `np.expm1`,
`np.isfinite`, and `isinstance` checks against `np.integer`/`np.floating`.
scipy is `brentq`, plus the base-class `quad` fallback that is already lazily
imported inside the method. Every call site of `forward_age`/`inverse_age` in
`plotting.py`, `examples/`, `docs/` and the paper is **scalar, inside a Python
list comprehension** — nothing is vectorized.

### The stdlib replacements are bit-identical

I prototyped both substitutions and compared against the current code:

| Substitution | Result |
| --- | --- |
| `math.exp`/`math.expm1` vs `np.exp`/`np.expm1`, over every `k`/`dt` the model uses | **max relative difference 0.0 — bit-identical** |
| ~50-line pure-Python Brent vs `scipy.optimize.brentq`, inverting `forward_age` at targets from 1 yr to `max_secular_age` | **max relative difference 0.0 — bit-identical** |

Both are libm calls underneath, so this is expected, but it is worth having
confirmed: the refactor cannot move a single digit, and
`tests/test_characterization.py` will pass unchanged.

### What that saves, in bytes

Pyodide 314.0.3, measured from the CDN:

| | raw | over the wire |
| --- | --- | --- |
| Pyodide core (`pyodide.asm.wasm` + `python_stdlib.zip` + js) | 11.59 MB | **5.82 MB** |
| numpy wheel | 2.78 MB | 2.78 MB |
| scipy wheel | 13.36 MB | 13.36 MB |

So: **~22 MB if `card.models` keeps importing numpy and scipy, ~5.8 MB if it
doesn't.** The two wheels are 2.8× the size of the entire Python runtime.
5.8 MB, brotli-compressed and browser-cached after first visit, is a normal
payload for a rich web app — this is the difference between "unshippable" and
"fine."

That is why my earlier objection to Pyodide doesn't survive: it was costed
against a dependency the model path doesn't need.

## 3. Architecture

```
┌─ main thread ────────────────┐     ┌─ Web Worker ──────────────────┐
│  React UI                    │     │  Pyodide runtime              │
│  ├─ preset picker            │     │  └─ card wheel (built in CI   │
│  ├─ parameter controls       │◄───►│      from this repo)          │
│  ├─ SVG charts               │ RPC │      ├─ card.models           │
│  └─ CSV download button      │     │      ├─ card.calibrate        │
│                              │     │      └─ card.series  (new)    │
│  ModelSource (async iface)   │     │                               │
│  ├─ PrecomputedSource ───────┼─────┼─► static JSON, instant        │
│  └─ PyodideSource ───────────┼────►│   live, arbitrary inputs      │
└──────────────────────────────┘     └───────────────────────────────┘
```

**Pyodide runs in a Worker, not on the main thread.** Non-negotiable: a
multi-second interpreter boot on the main thread means a frozen page, and
per-keystroke recalculation would jank the UI. In a Worker the page is
interactive immediately and calibration runs off-thread.

**`ModelSource` is an async interface** with two implementations:

```ts
interface ModelSource {
  calibrate(inputs: Inputs): Promise<Calibration>
  series(cal: Calibration, n: number): Promise<Row[]>
  forwardAge(cal: Calibration, trueAge: number): Promise<number>
  inverseAge(cal: Calibration, secularAge: number): Promise<number>
}
```

`PrecomputedSource` reads a small static JSON of the presets, generated in CI
by the same Python code. `PyodideSource` calls `card` for real. The UI never
knows which is answering.

### The boot experience

This is where the two sources earn their keep, and it's the main UX risk to
design around:

1. **t=0** — page paints. `PrecomputedSource` is already loaded (~40 kB
   gzipped), so the default preset's chart is on screen immediately. Parameter
   controls are visible but disabled, with a quiet "preparing live model…"
   indicator.
2. **t≈2–4 s** — the Worker signals ready. `ModelSource` swaps to
   `PyodideSource`, controls enable. If the user changed presets in the
   meantime, the precomputed layer already served it.
3. **thereafter** — every interaction is a real `card` call, ~5 ms of compute
   plus worker round-trip.

A visitor who only wants to see the presets never waits. A visitor who wants
to drag sliders waits a few seconds once, then never again. Cold-start cost is
paid in the background rather than in front of a spinner.

If measurement shows boot is worse than ~4 s on a mid-range phone, the fallback
is to load Pyodide lazily on first interaction with a parameter control, rather
than eagerly on page load.

## 4. Package changes — the enabling work

All of this lands in `src/card/` as ordinary package improvement, reviewable on
its own, valuable independent of the frontend. It runs *with* the repo's
existing grain: `__init__.py` is already lazy, `config.py` is already
stdlib-only, `chronology.py` and `parameters.py` are already numpy-free. This
extends that gradient to the last two modules that matter.

**4.1 — `card/_solvers.py` (new).** Pure-Python Brent, ~60 lines, same
signature and tolerances as `scipy.optimize.brentq`. Verified bit-identical
above.

**4.2 — `models.py` and `calibrate.py` go stdlib-only.**
- `np.exp`/`np.expm1`/`np.isfinite` → `math.exp`/`math.expm1`/`math.isfinite`.
- `scipy.optimize.brentq` → `card._solvers.brentq`.
- The `isinstance(value, (int, float, np.integer, np.floating))` checks →
  `isinstance(value, numbers.Real)`. This is strictly *better*, not a
  workaround: `numbers.Real` already covers `np.float64` and `np.int64` via
  ABC registration, so numpy scalars keep working for callers who pass them,
  while the module stops importing numpy to find that out. The existing
  `isinstance(value, bool)` guard stays and must stay first, since `bool` is
  `Integral`.
- The `quad` fallback in `DecayModel.compute_integral` keeps its lazy scipy
  import. It is the base-class path for hypothetical future models with no
  closed form; `GeneralModel` and `ConstantDecayModel` both override it, so
  nothing on the frontend path can reach it. Under Pyodide it would raise
  `ImportError`, which is the honest outcome — a model without a closed form
  isn't a browser model.

**4.3 — extend `tests/test_package_structure.py`.** That file already asserts
`import card` pulls in nothing heavy. Add the same assertion for
`import card.models` and `import card.calibrate`:

```python
assert not {"numpy", "scipy"} & set(sys.modules)
```

This is the whole drift-protection story, and it is one assertion in the Python
test suite rather than a parity harness in the frontend. **If someone adds
`import numpy` to `models.py` two years from now, pytest fails in this repo** —
they find out immediately, not when a user's download quietly grows by 16 MB.

**4.4 — `card/series.py` (new).** Time-series sampling and CSV emission,
shared by the web app and a new `card series` CLI subcommand. The web
download and the CLI output then come out of one function, so a CSV a user
downloads from the site is byte-identical to one they'd generate locally.
Details in §7.

**4.5 — keep `numpy`/`scipy` as package dependencies.** `inference.py` and
`plotting.py` genuinely need them. Nothing about the install changes; the
frontend just installs the wheel into Pyodide with `micropip.install(...,
deps=False)` because the modules it imports have no such imports to satisfy.

## 5. Directory layout

`web/` is self-contained — own `package.json`, own lockfile, own CI workflow —
so `git subtree split --prefix=web` extracts it with full history later.

```
web/
  package.json  vite.config.ts  tsconfig.json  index.html  README.md
  presets/
    presets.json              # single source of truth; read by TS and Python
  tools/
    build_wheel.sh            # builds the card wheel from ../ into public/
    generate_precomputed.py   # imports card; emits the first-paint JSON
  public/
    pyodide/                  # vendored runtime (not committed; see §8)
    card-0.1.0-py3-none-any.whl
    precomputed.json
  src/
    worker/
      pyodide.worker.ts       # boots Pyodide, installs the wheel, exposes RPC
      bridge.py               # thin Python called by the worker
    model/
      ModelSource.ts          # the interface
      PyodideSource.ts
      PrecomputedSource.ts
      types.ts
    charts/    AgeComparisonChart.tsx  LambdaHistoryChart.tsx  axes.ts  format.ts
    ui/        App.tsx  PresetPicker.tsx  ParameterPanel.tsx
               CalibrationReadout.tsx  AgeConverter.tsx
    styles/
```

**`src/worker/bridge.py` is where the Python/JS boundary lives.** Keeping it a
real `.py` file rather than strings inside TypeScript means it is lintable,
testable from pytest, and diffable. It should be thin — parameter dict in,
plain dict out — so that all the logic stays in `card` where it is already
tested.

## 6. Presets

The two axes are different kinds of thing and the UI should say so:

- **Chronology** (LXX vs Masoretic) changes `age_of_earth` and the event DATEs
  — the timeline itself.
- **Boundary** (K/Pg vs N/Q) changes the *secular target* of the matched date
  pair — which stratigraphic boundary is identified with the Flood.

So a preset is `chronology × boundary`, presented as two dropdowns, with the
second constraint (end of the Ice Age, 11.5 kyr apparent) held across all of
them. Selecting a preset runs the calibration and **fills in the parameter
controls**, so the relationship between preset and inputs is visible rather
than magic; touching a control moves you to "custom" and shows how far the
constraints are now missed.

### Feasibility: verified

I ran the full matrix through `solve_flood_only`. Every cell solves exactly,
at machine-precision residuals:

| Chronology | Boundary | λ_F | k_F | max residual |
| --- | --- | --- | --- | --- |
| Masoretic | PC–Cambrian 540 Ma | 3.224e6 | 5.970e-3 | 1.1e-16 |
| Masoretic | K/Pg 66 Ma | 3.188e5 | 4.830e-3 | 8.9e-16 |
| Masoretic | N/Q 2.58 Ma | 7.910e3 | 3.071e-3 | 7.1e-15 |
| LXX* | PC–Cambrian 540 Ma | 3.263e6 | 6.043e-3 | 8.9e-16 |
| LXX* | K/Pg 66 Ma | 3.233e5 | 4.900e-3 | 3.3e-16 |
| LXX* | N/Q 2.58 Ma | 8.072e3 | 3.135e-3 | 8.9e-16 |

\* LXX = `age_of_earth=7500, flood_start_date=2262, ice_age_end_date=4100`.
**Accepted as the working values for build purposes.** They still want a
citation and a review pass from Rick before the site is published — wrong
chronology numbers are invisible to every test in this plan, since the tests
only check that the model computes correctly on whatever it is given. Tracked
as a pre-publication checklist item in §13, not a blocker on implementation.

The point is that the solve is robust across the whole matrix; there's no
hidden bracket-widening problem waiting.

`web/presets/presets.json` is authored once and read by both sides — TypeScript
imports it, `generate_precomputed.py` reads the same file — so a preset can't
be defined in the app in a form Python never validated.

## 7. Free parameters

This is the core use case, so it gets the care.

**Scope for v1: the flood-only pair, `lambda_F` and `k_F`.** The Creation-week
parameters (`lambda_c`, `k_c`, `t_c`) stay fixed at their flood-only limit. But
nothing in the design may *encode* that choice — expanding to the full general
model has to be a data change, not a rewrite.

### Modes are data, not code

The package already has the right concept, and the shipped run config already
uses it — the `fixed:` block in
[flood_only.yaml](src/card/data/flood_only.yaml). A mode is exactly that: a
mapping of pinned parameters. Free parameters are whatever is left, computed by
`parameters.split_fixed_and_free()`, which also already exists.

```jsonc
// web/presets/presets.json
"modes": {
  "flood_only": {
    "label": "Flood only",
    "default": true,
    "fixed": { "lambda_c": 1.0, "k_c": 0.0, "t_c": 1.0,
               "t_F": "flood_start_date", "t_F2": "flood_end_date" }
  },
  "general": {                     // authored now, not exposed in v1
    "label": "Creation week + Flood",
    "enabled": false,
    "fixed": { "t_c": 1.0, "t_F": "flood_start_date", "t_F2": "flood_end_date" }
  }
}
```

Turning on the general model is then flipping `enabled` — no component changes.

**The rule that makes this work:** `ParameterPanel` renders by iterating the
free names returned from Python, never over a literal
`['lambda_F', 'k_F']`. Controls are generated from
`to_json_schema(GeneralModelParams, chronology=...)` — which already exists and
already returns chronology-aware date bounds — **fetched from Pyodide rather
than transcribed into TypeScript.** Log sliders where `x-log-scale` is set,
linear otherwise, `lambda_bg` absent because its `is_fittable` is false. Add a
parameter to the dataclass and a control appears with no frontend change at
all; that property is the whole reason for running the real package in the
browser, and it should be *tested* — a unit test asserting the panel renders
N controls for a mode with N free names, run against both modes.

### The calibration survives the expansion — verified

The obvious worry is that freeing `lambda_c`/`k_c` breaks the deterministic
solve: `solve_flood_only` is two constraints for two unknowns, and four
unknowns would be underdetermined.

It doesn't, because **the two constraints are exactly insensitive to the
Creation-week parameters.** Both constraint ages (Flood 4400 YBP, Ice Age end
2556 YBP) map to formation DATEs at or after `t_F`, so their integrals cover
only regions 3 and 4 — `lambda_c` and `k_c` never enter. I measured it across
three very different Creation-week settings:

| Creation-week setting | Δ at Flood constraint | Δ at Ice Age constraint | effect at 6055 YBP |
| --- | --- | --- | --- |
| `lambda_c=1e5, k_c=0.1` | **0.000e+00** | **0.000e+00** | ×1.015 |
| `lambda_c=1e8, k_c=1e-3` | **0.000e+00** | **0.000e+00** | ×1227 |
| `lambda_c=1e3, k_c=0` | **0.000e+00** | **0.000e+00** | ×1.025 |

Exactly zero, not merely small. So the expansion is clean and needs no new
solver: `solve_flood_only` keeps pinning `lambda_F`/`k_F` from the two
constraints, and `lambda_c`/`k_c` become free *inputs* that reshape the curve
only for true ages older than the Flood. The calibration readout stays honest
in both modes, because the residuals it reports genuinely don't move.

That also tells the UI something worth saying out loud: in the general mode,
the Creation-week controls are exploratory rather than fitted, and the chart
should mark the pre-Flood region as the only part they affect.

### Validation

Validation is the package's, not the frontend's.
`GeneralModelParams.__post_init__` raises `ValueError` with prose already
written for a human, so the bridge catches it and the UI renders the message
verbatim. The two *warnings* (Flood duration > 2 yr, `lambda_bg != 1`) surface
as non-blocking notices via `warnings.catch_warnings`. A user who types a DATE
into an AGE field gets the package's own explanation of the difference.

This matters more in the general mode than in v1: `t_c <= t_F <= t_F2` ordering
and the `lambda >= 1` floor become reachable by ordinary slider fiddling once
more controls exist. Building against the real validator now means that mode
arrives already handled.

Debounce parameter changes at ~100 ms. At 5 ms per solve there's headroom, but
a dragged slider fires far faster than it needs recomputing.

## 8. CSV export

Generated **by Python, in the browser**, through the new `card/series.py` —
same function behind the proposed `card series` CLI subcommand, so a download
from the site and a local CLI run produce identical bytes.

Sampling grid: log-spaced in true age (the structure is all in the recent end;
a linear grid spends every point on the flat tail), unioned with the exact
breakpoints ±ε so the Flood discontinuity is a step rather than a diagonal
artifact, and with each constraint's age so the calibration anchors are exact
rows. ~400 rows for the chart, user-selectable to ~20,000 for the download.

```
# CARD calibrated time series
# generated: 2026-08-04T00:00:00Z   card 0.1.0 (commit abc1234)
# preset: Masoretic chronology / K/Pg boundary   [or: custom parameters]
# chronology: age_of_earth=6056 flood_start_date=1656 flood_end_date=1656 ice_age_end_date=3500
# parameters: lambda_F=318754.xxx k_F=0.00482991xxx lambda_c=1 k_c=0 t_c=1 t_F=1656 t_F2=1656
# constraint: Flood 4400 YBP -> 66000000 yr apparent (residual 8.9e-16)
# constraint: Ice Age end 2556 YBP -> 11500 yr apparent (residual -1.2e-16)
true_age_ybp,formation_date_yac,secular_age_yr,lambda_at_formation,acceleration_ratio
```

Two notes. The provenance header isn't decoration — a CSV that leaves the page
without its chronology and parameters is an unreproducible number, and with
free inputs most downloads will be of parameter sets that exist nowhere else.
And `#` comment lines are read as comments by pandas (`comment='#'`) and R
(`comment.char='#'`) but **not** by Excel, which shows them as rows. If
Excel-first matters, say so and I'll emit a flat header plus a sidecar `.json`.

Column names follow the repo's convention: `_ybp`/`_yac` suffixes so a DATE
can't be mistaken for an AGE in a downloaded file.

## 9. Build and deploy

**One conflict.** GitHub Pages allows one site per repo, and
[docs.yml](.github/workflows/docs.yml) already owns it. Resolution: build the
app into the docs site after `mkdocs build --strict`, with Vite's
`base: '/card-model/app/'`, so it lands at `…github.io/card-model/app/` as one
deployment. When `web/` splits out, that step is deleted — the coupling is five
lines of YAML.

**Vendor Pyodide; don't hit a CDN at runtime.** The `pyodide` npm package is
copied into `public/pyodide/` at build time (not committed). Costs ~12 MB in
the Pages artifact — irrelevant against Pages' 1 GB limit — and buys no
third-party runtime dependency, no CDN outage, a strict CSP with no
`script-src` exceptions, and a build that is reproducible from the lockfile.

**Build the `card` wheel in CI from the repo itself**, don't install from PyPI.
`python -m build --wheel` → `web/public/*.whl`. The app then always runs the
code in the commit that deployed it. This is what makes the whole approach
drift-free: the model in the browser *is* the model in `src/`, not a version of
it.

**`web.yml`** (new) tests and builds on PRs touching `web/**` or `src/card/**`;
it never deploys.

**Gotcha:** `.gitignore` ignores `*.png`/`*.jpg`/`*.jpeg` repo-wide for the
generated figures. Any committed app asset — favicon, OG image — vanishes
silently. Needs a `!web/public/**` negation.

## 10. Phases

**Phase 1 — package work (no frontend at all).** §4.1–4.3: `_solvers.py`, the
stdlib-only conversion, the extended structure test. Ends when the full pytest
suite passes unchanged — and it should pass *unchanged*, because the
substitutions are bit-identical. Reviewable as a self-contained package PR
that's worth merging on its own merits.

**Phase 2 — Pyodide spike.** Worker boots, installs the wheel, calls
`solve_flood_only`, returns a number to the page. No UI, no charts. **Measure
real boot time and payload on a throttled connection and a mid-range phone.**
This is the go/no-go gate: if boot is unacceptable here, we fall back to
lazy-load-on-interaction, and if *that* fails, to a local-only `card serve`
backend with a precomputed public site. Cheap to run, and it de-risks
everything after it.

**Phase 3 — `ModelSource` + presets.** Both implementations, `presets.json`,
`generate_precomputed.py`, the first-paint/live swap. Testable headlessly.

**Phase 4 — app shell and charts.** Vite + React, the two charts
(`plot_age_comparison` and `plot_lambda_history` analogues), preset picker,
calibration readout. First thing you can look at.

**Phase 5 — free parameters.** Schema-driven controls driven by the mode's
free-name list, debounced live recalibration, validation messages piped from
the package, the two-way age converter. Ships `flood_only` only, but the
`general` mode is authored in `presets.json` and **exercised in tests** from
this phase onward — an unexercised expansion path is a claim, not a
capability.

**Phase 6 — CSV.** `card/series.py`, the `card series` subcommand, the
provenance header, the download. Test asserting the CSV's anchor rows equal
the constraint targets.

**Phase 7 — CI, deploy, polish.** `web.yml`, the `docs.yml` mount step, the
`.gitignore` negation, responsive layout, dark mode, `web/README.md` written as
the future standalone repo's README.

Phases 1 and 2 are the ones that decide whether this plan is right. Everything
after them is ordinary app construction.

## 11. Charting

Recommend **d3-scale + d3-shape with hand-written SVG components** (~15 kB).
The requirement is log axes spanning 1 → 5.4e8, a step discontinuity that must
not be smoothed, and scientific tick labels; Recharts fights all three and
Plotly solves them at 3 MB — which would be absurd next to a 5.8 MB runtime we
just worked to justify. **uPlot** (~45 kB) is the fallback if pan/zoom becomes
a hard requirement.

Light/dark following `prefers-color-scheme`, to sit next to the
mkdocs-material site.

## 12. Open questions

**Settled.** LXX chronology values — using `7500 / 2262 / 2262 / 4100`, pending
a citation review before publication (§13). User-facing parameters — the
flood-only pair `lambda_F`/`k_F` for v1, with the general model authored and
test-exercised but not exposed (§7).

**Still open:**

1. **Is the second constraint always the end of the Ice Age at 11.5 kyr?** The
   preset shape assumes yes across the whole matrix.
2. **K/Pg and N/Q secular ages** — I used 66.0 Ma and 2.58 Ma (ICS). Confirm,
   and give me the uncertainties to display.
3. **Should users be able to edit the chronology freely**, or only choose
   between named ones? Free editing is nearly free to build — `Chronology`
   validates itself — but it lets people build timelines nobody vetted. Note
   this is a *separate* axis from §7's parameter modes: `t_F`/`t_F2` are pinned
   to chronology names in every mode, so a freely-edited chronology moves them
   even in v1.
4. **MCMC in the UI?** Assumed out of scope; posteriors stay in the docs
   gallery. If you want credible bands later, the honest answer is a
   precomputed chain summary shipped as JSON, not sampling in the browser.
5. **Excel or pandas for the CSV?** Drives the header decision in §8.

## 13. Pre-publication checklist

Things that no test in this plan can catch, because they are content rather
than code — the suite only checks that the model computes correctly on whatever
it is handed.

- [ ] LXX chronology values reviewed by Rick, with a citation displayed in the
      UI next to the preset.
- [ ] Masoretic values confirmed as still matching `DEFAULT_CHRONOLOGY` at
      time of release.
- [ ] Boundary secular ages and uncertainties confirmed against ICS.
- [ ] Wording of the model's framing and caveats reviewed — the app will be
      the most-read surface this project has, and it should be at least as
      careful as the paper about what is assumed versus derived.

## 14. Risks

- **Pyodide boot time** — the main UX risk, measured at Phase 2, mitigated by
  the precomputed first-paint layer and the lazy-load fallback.
- **Payload regression** — someone reintroduces numpy to `models.py` and the
  download silently grows 16 MB. Guarded by the §4.3 pytest assertion, which
  is why that assertion is part of the plan rather than a nice-to-have.
- **Mobile memory** — Pyodide holds ~50–100 MB resident. Fine on modern
  phones; verify on a low-end device in Phase 2.
- **Worker/main-thread complexity** — real, but bounded, and the `ModelSource`
  interface confines it to one file.
- **The expansion path rots** — the `general` mode is authored but not shipped,
  and unexercised paths break silently. Mitigated by testing both modes from
  Phase 5 on; if that testing is dropped, treat the expansion claim as
  unsupported.
- **Preset numbers are content, not code** — see the §13 checklist.
- **Repo split friction** — low. `web/tools/` gains a `pip install card-model`
  dependency on split, which is correct.
