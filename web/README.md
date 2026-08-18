# CARDulator

The web front end for the CARD model. It runs the **real `card` Python
package** under Pyodide rather than reimplementing the model in TypeScript, so
there is exactly one implementation of the numerics and it is the tested one.

The name is the front end's, not the model's: `card` stays `card` on PyPI and
in every import. Only this app is CARDulator.

Self-contained: own `package.json`, own lockfile, own CI workflow, so
`git subtree split --prefix=web` extracts it into its own repository later.

**Status: Phase 7**, on the three-exponential model the authors landed in
PR #12. Charts, free parameters, the age converter, the CSV export and the
deploy are built. Known gaps are tracked in [OPEN_ITEMS.md](OPEN_ITEMS.md) —
two of them (the provisional Septuagint chronology and the unverified ICS
boundaries) block publication, and neither is catchable by any test here. See
`../frontend_plan.md` for the phased plan and
[`spike/README.md`](spike/README.md) for the Phase 2 measurements that shaped
the architecture.

## Setup

Requires **Node 20.12+** (`.nvmrc` pins 22) and Python with the `card` package
importable from `../src`.

```bash
cd web
nvm use           # Node 18 is EOL and cannot run vitest 4 / vite 8
npm install
npm run setup     # build the card wheel, vendor Pyodide, regenerate presets
npm test          # fast unit tests
npm run test:live # boots a real Pyodide interpreter (~2 s)
npm run dev       # the app at http://localhost:8423
```

`npm run build` produces the static bundle. The deploy sets `VITE_BASE`, since
the app is mounted inside the docs site rather than at a domain root — see
[Deployment](#deployment).

`/harness.html` on the same server is a **developer harness** kept from Phase 3.
The headless tests use `DirectTransport` in Node, so it is still the only thing
that exercises the Worker path by hand, and it is where the Phase 2 boot stall
would be reproduced.

## The three charts

**Apparent age vs. true age** mirrors `card.plotting.plot_age_comparison`: two
series on log-log axes, the model against the constant-rate reference where
apparent equals true. The gap between them is the claim. The curve has a *kink*
at the Flood, not a step — `forward_age` is the integral of a bounded rate and
so is continuous.

It **toggles between two orientations**, because there are two questions and
they are not the same one. `True → apparent` is the model's forward map, both
axes logarithmic, and is the figure the package draws. `Apparent → true` puts
the published radiometric age on x and the young-earth age on a **descending**
linear y — most recent at the top, the way a stratigraphic column is drawn.
That is the direction a reader usually arrives from: they have a secular age
and want the young-earth date. In that orientation the constant-rate reference
is a curve rather than a straight line (log x against linear y), so it is
sampled rather than drawn end-to-end.

**Decay rate through time** mirrors `plot_lambda_history`. Its x axis is a
**DATE** — years after Day 1 of Creation — the only chart in the app running
that direction, and the convention whose confusion once caused a real fitting
error in this package. This curve *does* step at the Flood, so its grid carries
two samples a fraction of a year apart and the generator refuses to emit a
version where rounding has collapsed them.

**The geological column in young-earth time** has no counterpart in the
package. One horizontal bar per ICS unit, spanning the true ages its secular
boundaries map to, with time running right to left and a secondary calendar-date
axis. Units the calibration cannot reach get a marked empty row rather than
being dropped — pinning the Flood to K/Pg caps the model at 66 Myr, so nine of
the fourteen have no young-earth date at all, and an empty row says that where
an omission would not.

Its durations are **precomputed exactly in Python**, not derived in the browser.
A duration is the difference of two inverse ages that agree to four or five
significant figures; interpolating at the precomputed layer's ~0.03% would put
13.7% error on the Silurian. Unit boundaries live in `data/ics-units.json` and
are **provisional** until checked against the published ICS chart.

Colors are the first two categorical slots of the reference palette, validated
in both modes: worst CVD separation ΔE 24.7 light / 26.8 dark against a ≥ 8
target, contrast ≥ 3:1. Both charts carry a crosshair tooltip and a collapsed
data table, so no value is reachable only by hovering a chart.

## How it fits together

```
      ┌──────────────────────────────────────────────┐
      │  ModelSourceManager   — owns which is live    │
      └───────────┬───────────────────┬──────────────┘
                  │                   │
     PrecomputedSource            PyodideSource
     public/precomputed.json      Worker → Pyodide → card
     instant, ±1%                 ~12-42 s to boot, exact
```

**`ModelSource`** is the seam. Every method is async even where one
implementation could answer synchronously — the live source is genuinely across
a worker boundary, and retrofitting sync-to-async through a component tree later
is miserable.

**`PrecomputedSource`** reads four solved presets from a static ~60 kB (gzipped)
table generated by `card` itself. It is **not** an optimization: Pyodide is
5.84 MB and boot is essentially all download, so for the first 12–42 s of a
first visit this class is the entire application. It cannot solve — a request
with custom parameters gets `UnsupportedRequestError`, and the caller's response
is to boot the live source.

**`PyodideSource`** calls `card` for real, through `src/worker/bridge.py`. It
holds no model logic, deliberately.

**`ModelSourceManager`** decides when Pyodide starts. **It does not start on
page load.** That is the direct consequence of the Phase 2 measurements: 42 s to
download at a measured 142 kB/s, ~12 s at 4 Mbps. It starts when the user
touches something that needs it, or after an optional idle delay. Someone who
only wants to look at the presets never pays the cost.

## Accuracy

The precomputed layer interpolates in log-log space, valid because `forward_age`
is monotone (it is the integral of a non-negative rate). Measured against the
live model at grid midpoints, worst case across all four presets:

| | worst error | usable for |
| --- | --- | --- |
| forward age | 0.77% | charts (sub-pixel on a log axis) |
| inverse age | 0.86% | charts |

Both grew when `k_F` sharpened the curve: just younger than the Flood,
`forward_age` climbs by the whole post-relaxation integral, so the grid refines
log-spaced in time-since-the-breakpoint over the window where the rate is still
moving — computed from the model, since `k_F` and `k_PF` differ by three orders
of magnitude and one fixed window would suit neither.

Too coarse to quote as an exact figure, which is why `ModelSource.exact` exists
and why the UI must mark interpolated scalars. The solved *parameters* and
residuals are not interpolated — the generator ran the real solver — so those
are exact in both sources.

## The three matched pairs

The package's model now relaxes at **two** rates, so three pairs fix it:

1. **Flood onset ↔ the pre-Flood contact** (Precambrian–Cambrian, 541 Ma).
2. **Flood onset + 1 year ↔ the post-Flood contact** you select (K/Pg or N/Q).
3. **End of the Ice Age ↔ a conventional Ice Age endpoint** (12 ka).

λ starts at `lambda_F`, relaxes across the Flood year at `k_F`, and hands the
post-Flood exponential whatever it has reached at `t_F2`. That handover is
**continuous** — `lambda_F2` is a read-only property, not a free parameter —
which is what makes `k_F` one new degree of freedom rather than two. λ still
steps *up* at `t_F`: the onset is the model's one genuine discontinuity.

Masoretic / K-Pg comes out at:

| | |
| --- | --- |
| λ_F | 4.55e9 × background |
| k_F (in Flood) | 9.571 /yr |
| k_PF (after) | 0.00480 /yr |
| λ at the Flood's end | 3.17e5 × — a 14,300× drop inside the year |

The two rates differ by a factor of 2,000, which is exactly what a single `k`
could not express: pinning only the Flood year's two ends forced
`k × 1 yr = ln(pre/post)`, so the relaxation was spent within a decade and the
Cenozoic collapsed. `card`'s reference figures for the same solve are λ_F 4.53e9,
k_F 9.56, k_PF 4.83e-3 — the small differences are its 540 Ma / 11.5 kyr anchors
against the author's 541 Ma / 12 ka used here.

> **Chronology caveat.** The Masoretic entry follows the package default, where
> `ice_age_end_date` is a DATE and the Ice Age ends at 2556 BP. The Septuagint
> entry is provisional: the Flood at 5324 BP is the author's figure but
> `age_of_earth` is still a placeholder, so the two are **not on the same
> footing** until Rick confirms them.

## Presets are data

`presets/presets.json` is the single source of truth, read by both TypeScript
and Python, so a preset cannot be defined in the app in a form Python never
validated. It carries chronologies, boundaries, and **modes**.

A mode is a mapping of pinned parameters — the same concept as the `fixed:`
block in the package's own run config. Free parameters are whatever is left,
computed by `card.parameters.split_fixed_and_free`. v1 ships `flood_only`;
`general` (Creation week + Flood) is authored with `enabled: false` and is
**exercised in the live tests**, because an unexercised expansion path is a
claim rather than a capability.

Turning the general model on is flipping that flag. It needs no new solver:
both constraint ages map to formation DATEs at or after `t_F`, so their
integrals never touch `lambda_c` or `k_c`. The live suite pins this at *exactly*
zero difference.

> **The Septuagint chronology values are placeholders** (`7500 / 2262 / 2262 /
> 4100`) pending review and a citation. They are flagged `provisional: true` in
> the data so the UI can say so, and they are on the pre-publication checklist
> in `../frontend_plan.md`.

## Changing the parameters

The controls are generated from the package, not written here. `ParameterPanel`
renders whatever names `to_json_schema(GeneralModelParams)` returns and reads
each control's range, unit, scale and tooltip from the `ParamSpec` on the
dataclass field — so adding a parameter to `GeneralModelParams` makes a control
appear with no change to the front end. Two consequences worth knowing:
`lambda_bg` is skipped because its spec has `minimum == maximum`, and `k_F` is
linear where the other rates are logarithmic because its spec says so.

Moving a control is what boots Pyodide: the precomputed layer only holds the
presets, so anything else needs the real model. The panel warns before that
5.8 MB download rather than freezing on it.

When the model rejects a combination, its own words are shown. Every slider is
clamped to its own spec, so no single parameter can leave its range — but
nothing about a per-parameter bound catches a rule *between* parameters, and
`GeneralModelParams` explains `t_c <= t_F <= t_F2` better than a generic
"invalid input" could.

## Converting an age

Type a published radiometric age and get the young-earth date, or the reverse.
Both directions are `forward_age`/`inverse_age` on the calibration in force. One
field is authoritative and the other derived — holding them as peers made every
answer schedule another conversion. Out-of-domain input shows the package's own
prose, which names the oldest apparent age the model can produce and why.

## Downloading the series

`card.series.to_csv` writes the file, inside Pyodide — the same function behind
`card series`, so a download here and a local CLI run are **byte-identical** for
the same model, grid and timestamp. A live test asserts that against a real CLI
run rather than assuming it.

The grid is log-spaced, because a linear one over six thousand years spends
almost every point on the flat tail and none inside the Flood year where λ falls
four orders of magnitude. The breakpoints are unioned in so the jump at `t_F` is
a step, and so are the constraint ages, so the calibration's anchors are exact
rows.

Every file opens with a provenance header carrying the chronology, every
parameter and each constraint's residual. That is not decoration: readers can
move the parameters, so most downloads describe a model that exists nowhere
else. `#` lines are comments to pandas and R, but not to Excel.

## Power-user mode

A checkbox in the header strips the explanatory prose and tightens the spacing,
remembered in `localStorage`. It hides *explanation* only — warnings, errors,
units and the `≈` marking on interpolated values are shown in every mode, and
the per-parameter descriptions are visually hidden rather than removed so
`aria-describedby` still resolves.

## Deployment

GitHub Pages allows one site per repo and `docs.yml` owns it, so the app is
built into the docs site at **`/card-model/app/`** rather than deployed
separately. Four steps at the end of that workflow install the web
dependencies, build the wheel and vendor Pyodide, build with
`VITE_BASE=/card-model/app/`, and copy `web/dist` to `site/app`. When `web/`
splits into its own repository those steps are deleted and nothing else
changes.

`web.yml` runs on PRs touching `web/**` or `src/card/**`: typecheck, unit tests,
a build, and the live suite against a real Pyodide interpreter and a wheel built
from the checkout. It never deploys.

Two things are vendored rather than fetched at runtime. **Pyodide** is copied
from the npm package at build time — no CDN outage, no `script-src` exception,
a build reproducible from the lockfile. And the **`card` wheel is built from
this checkout**, never installed from PyPI, so the model running in the browser
is the model in `src/` at the commit that deployed it.

## Layout

| | |
| --- | --- |
| `presets/presets.json` | single source of truth; read by TS and Python |
| `tools/generate_precomputed.py` | emits the first-paint layer; `--check` guards staleness |
| `tools/build_wheel.sh` | builds the `card` wheel from this repo |
| `tools/vendor-pyodide.mjs` | copies the runtime out of `node_modules` |
| `src/model/` | `ModelSource` and its two implementations |
| `src/worker/` | Pyodide runtime, transports, and `bridge.py` |
| `src/charts/` | the three figures, plus the breakpoint markers |
| `src/ui/` | the shell, the panels, and the persisted preferences |
| `public/precomputed.json` | generated, **committed** — deployed content |
| `spike/` | the Phase 2 go/no-go measurements |

`src/worker/bridge.py` is a real `.py` file rather than a string inside
TypeScript, so it is lintable, diffable, and importable from pytest. It is
thin — dicts in, dicts out — so all the logic stays in `card`.

## Why the wheel is built here

`tools/build_wheel.sh` builds from the checkout rather than installing from
PyPI, so the model running in the browser is the model in `src/` at the commit
that deployed it. That is what makes the approach drift-free, and it is why
there is no parity harness: there is nothing to keep in parity.
