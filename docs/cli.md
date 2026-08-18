# Run configs and CLI

A **run config** is one YAML (or JSON) file describing a whole fit: the
chronology, the matched date pairs, which parameters are pinned, the priors and
the sampler settings. It is the file form of `examples/run_card_mcmc.py`, so
exploring a different chronology or a different constraint set is an edit to a
config rather than an edit to a script.

```bash
card init myrun.yaml         # write a documented starter config
card fit myrun.yaml          # run the MCMC, write chain + figures + summary
card calibrate myrun.yaml    # solve the same constraints exactly
card series myrun.yaml       # write the calibrated time series as CSV
card schema                  # print the parameter spec as JSON Schema
card --version
```

## A complete config

`card init` writes exactly this — the main inversion. It ships inside the
package, so it is available from a `pip install` with no repository checkout:

```yaml
chronology:
  age_of_earth: 6056
  flood_start_date: 1656
  flood_end_date: 1657
  ice_age_end_date: 3500

constraints:                          # three pairs, three unknown rates
  - young_age: flood_start_age        # 4400 YBP under the chronology above
    secular_age: 540.0e6
    uncertainty: 1.0e7
    label: Precambrian-Cambrian boundary
  - young_age: flood_end_age          # 4399 YBP — one year later
    secular_age: 66.0e6
    uncertainty: 1.0e5
    label: Cretaceous-Paleogene boundary
  - young_age: ice_age_end_age        # 2556 YBP
    secular_age: 11500.0
    uncertainty: 30.0
    label: end of the Ice Age

fixed:                                # linear units, always
  lambda_c: 1.0                       # k_F is absent: it is fitted now
  k_c: 0.0
  t_c: 1.0
  t_F: flood_start_date
  t_F2: flood_end_date

priors:                               # in each parameter's sampling space
  lambda_F: {mean: 9.7, sigma: 1.0}   # log-scale, so these are log10
  k_F: {mean: 9.6, sigma: 5.0}        # linear — a one-year Flood
  k_PF: {mean: -2.3, sigma: 1.0}

sampler:
  n_walkers: 32
  n_steps: 20000
  burn_in: 5000
  seed: 20260731
  initial_guess: calibrate

output:
  directory: mcmc_output
  figures: true
```

Run it:

```bash
card init myrun.yaml
card fit myrun.yaml
```

which writes `chain.h5`, `run_config.json`, `summary_statistics.txt`,
`corner_plot.png`, `trace_plot.png` and `age_comparison_posterior.png` to
`mcmc_output/`.

## Sections

### `chronology`

Optional; omitted means the package default (Earth 6056 years old, an
Flood running from 1656 to 1657 years after Creation, Ice Age ending at
3500). Fields
are those of [`Chronology`](api/chronology.md). Whatever you set here governs
the whole fit, including the `present_time` that forward ages are measured
against.

### `constraints`

A list of matched date pairs. `young_age` is an **AGE** — years before present;
`uncertainty` is the standard deviation on `secular_age`, in years; `label` is
optional and appears in printed output. At least one is required.

`card fit` samples however many you give it. `card calibrate` solves them
exactly, so it needs the count to match the number of unknown rates:

| Pairs | Solves for | Via |
| --- | --- | --- |
| 2 | `lambda_F`, `k_PF` (at whatever `k_F` is pinned to) | [`solve_flood_only`](api/calibrate.md) |
| 3 | `lambda_F`, `k_F`, `k_PF` | [`solve_flood_rate`](api/calibrate.md) |

The three-pair solve reads its pairs by AGE, oldest first — the Flood's onset,
the Flood's end, then a later event — and takes those AGEs from the chronology.
A pair aimed somewhere else is refused rather than quietly resolved to the
chronology's value, so write `young_age: flood_end_age` and let it follow. Three
pairs also cannot come with a pinned `k_F`: it is what the third pair
determines.

### `fixed`

Parameters pinned to a value, in **linear** units regardless of how the
parameter is sampled. Anything not listed here (and not structurally
un-fittable, like `lambda_bg`) is free.

### `priors`

Gaussian priors, in each parameter's **sampling space** — log10 for the
log-scale parameters (`lambda_c`, `lambda_F`, `k_c`, `k_PF`), linear for
`k_F` and the times. Omitted parameters fall back to the spec's defaults.

### `sampler`

`n_walkers`, `n_steps`, `burn_in`, `seed`, `init_spread`, `progress`, and
`initial_guess`.

`initial_guess` is where the walkers start, in sampling space. It is either a
mapping of free-parameter names to values, or the string `calibrate`, which runs
the exact solve above — two pairs or three — and starts there. It is the same
code path as `card calibrate`, so the two cannot answer different problems from
one file.

!!! danger "Use it"

    The two-pair form of this fit has a second, far local maximum that traps
    walkers permanently. Started from the prior means, about a quarter of them
    fall in during burn-in and contaminate every percentile.
    `initial_guess: calibrate` is the cure; see
    [tutorial 2](tutorials/fitting.md#start-the-walkers-at-the-answer).

### `output`

`directory` (default `mcmc_output`) and `figures` (default `true`).

## Chronology names instead of numbers

Anywhere a number is expected you may write the **name** of a chronology
quantity, and the naming rule makes it unambiguous: a name ending in `_age`
resolves to an AGE (years before present), one ending in `_date` to a DATE
(years after Creation).

| Names | Resolve to |
| --- | --- |
| `flood_start_age`, `flood_age`, `flood_end_age`, `ice_age_end_age`, `creation_age` | AGEs |
| `flood_start_date`, `flood_end_date`, `ice_age_end_date`, `present_date`, `age_of_earth` | DATEs |

`t_F: flood_start_date` is therefore self-checking in a way `t_F: 1656` is not,
and it follows the chronology when you change it.

!!! note "YAML and exponents"

    YAML 1.1 does not read `540.0e6` as a number — it wants `540.0e+6`. Rather
    than fail on a missing plus sign, the loader accepts numeric-looking
    strings. Both spellings work.

## Overrides and exit status

Command-line flags win over the file, which is what makes a config reusable for
a quick check:

```bash
card fit myrun.yaml -o /tmp/quick --walkers 8 --steps 200 \
    --seed 1 --no-figures --quiet
```

| Flag | Overrides |
| --- | --- |
| `-o`, `--output` | `output.directory` |
| `--walkers` | `sampler.n_walkers` |
| `--steps` | `sampler.n_steps` |
| `--burn-in` | `sampler.burn_in` |
| `--seed` | `sampler.seed` |
| `--no-figures` | `output.figures` |
| `-q`, `--quiet` | the progress bar and the summary print-out |

A missing or invalid config exits **2** with a one-line message naming the
offending key — no traceback. Unknown keys are rejected rather than ignored,
because a misspelled `uncertianty` would otherwise fall back to a default and
quietly change the posterior.

## What a run leaves behind

`run_config.json` is written next to the chain. With chronology names resolved
and command-line overrides folded in, it is the only complete record of what
was actually run — worth keeping alongside any result you intend to cite.

## The calibrated time series

`card series` solves the config the same way `card calibrate` does, then writes
the model sampled over a grid of true ages:

```bash
card series myrun.yaml -o series.csv     # 400 rows by default
card series myrun.yaml -n 20000 > big.csv
```

The grid is log-spaced, because the structure is all at the recent end — a
linear grid over six thousand years spends almost every point on the flat tail
and none inside the Flood year, where λ falls by four orders of magnitude. The
model's breakpoints are unioned in so the jump at `t_F` is a step rather than a
diagonal, and so are the constraint ages, so the calibration's own anchors are
exact rows rather than interpolations between neighbours.

Every file opens with a provenance header:

```text
# CARD calibrated time series
# generated: 2026-08-17T12:00:00Z   card 0.1.0
# source: card series myrun.yaml
# chronology: age_of_earth=6056.0 flood_start_date=1656.0 ...
# parameters: lambda_c=1.0 k_c=0.0 t_c=1.0 lambda_F=... k_F=... k_PF=...
# lambda_F2: 318926.84149306716 (pinned by continuity at t_F2, not an independent parameter)
# constraint: Precambrian-Cambrian boundary: 4400.0 YBP -> 540000000.0 yr apparent (relative residual -8.9e-16)
true_age_ybp,formation_date_yac,secular_age_yr,lambda_at_formation,acceleration_ratio
```

That header is not decoration. The web app lets a reader move the parameters,
so most downloads describe a model that exists nowhere else, and a CSV without
its chronology and parameters is an unreproducible number. `lambda_F2` is
reported separately because continuity at `t_F2` pins it — feeding it back in
as a parameter would not round-trip.

`#` lines are comments to pandas (`comment='#'`) and R (`comment.char='#'`),
but **not** to Excel, which shows them as rows.

The web app's download button calls the same `card.series.to_csv`, so a file
fetched from the site and one written here are byte-identical for the same
model, grid and timestamp.

## Using configs from Python

`card.config` is stdlib-only (the YAML parser is imported inside the loader),
so a frontend or a web service can parse and validate a config without the
numerical stack installed:

```python
from card import RunConfig

config = RunConfig.from_dict({
    "constraints": [
        {"young_age": "flood_start_age", "secular_age": 5.4e8,
         "uncertainty": 1e7},
        {"young_age": "ice_age_end_age", "secular_age": 11500.0,
         "uncertainty": 30.0},
    ],
    "fixed": {"lambda_c": 1.0, "k_c": 0.0, "k_F": 0.0, "t_c": 1.0,
              "t_F": "flood_start_date", "t_F2": "flood_end_date"},
})
print(config.constraints[0].young_age, config.fixed_params["t_F"])
```

```text
4400.0 1656.0
```

`RunConfig.from_file` loads YAML or JSON; `build_fitter()` returns the
configured [`MCMCFitter`](api/inference.md); `solve_exactly()` runs the
deterministic solve and hands back the `CalibrationResult`, and
`calibrated_start()` reduces it to the linear starting values the sampler wants.

## Embedding CARD in an application

Everything the CLI does is available to a GUI or a web service, and a few
pieces exist specifically for that:

- **Reproducibility without global state.** `run_mcmc(seed=...)` — or
  `rng=numpy.random.default_rng(...)` — seeds the fit's own generator. Nothing
  in the package touches `numpy.random.seed`, so two fits in one process
  cannot disturb each other.
- **Progress and cancellation.** `run_mcmc(callback=...)` is called after every
  step with a `SamplingProgress` (`phase`, `step`, `total`, `fraction`,
  `acceptance_fraction`). **Return `False` to stop**; the results then carry
  `stopped_early=True` and describe the steps actually taken.
- **Figures you own.** Every plotting function takes `ax=` to draw into your
  canvas, or `return_figure=True` to hand back an open matplotlib `Figure`.
- **Forms that follow the chronology.** `to_json_schema(GeneralModelParams,
  chronology=...)` and `bounds_for_chronology(...)` give date parameters an
  upper bound from the chronology the user has loaded, not the default one.

```python
from card import MCMCFitter, RunConfig, example_config_text

config = RunConfig.from_dict(__import__("yaml").safe_load(example_config_text()))
fitter = config.build_fitter()

def on_step(progress):
    if progress.step % 20 == 0:
        print(f"{progress.phase} {progress.fraction:6.1%} "
              f"acceptance {progress.acceptance_fraction:.2f}")
    return True          # return False to cancel

results = fitter.run_mcmc(
    n_walkers=16, n_steps=60, burn_in=10, seed=0, progress=False,
    initial_guess=config.initial_guess_for(fitter), callback=on_step,
)
print(f"stopped early: {results['stopped_early']}, "
      f"steps: {results['n_steps']}")
```

```text

sampling  33.3% acceptance 0.67
sampling  66.7% acceptance 0.68
sampling 100.0% acceptance 0.69
stopped early: False, steps: 60
```
