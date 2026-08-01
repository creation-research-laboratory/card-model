# Run configs and CLI

A **run config** is one YAML (or JSON) file describing a whole fit: the
chronology, the matched date pairs, which parameters are pinned, the priors and
the sampler settings. It is the file form of `examples/run_card_mcmc.py`, so
exploring a different chronology or a different constraint set is an edit to a
config rather than an edit to a script.

```bash
card init myrun.yaml         # write a documented starter config
card fit myrun.yaml          # run the MCMC, write chain + figures + summary
card calibrate myrun.yaml    # solve the same two constraints exactly
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
  flood_end_date: 1656
  ice_age_end_date: 3500

constraints:
  - young_age: flood_start_age        # 4400 YBP under the chronology above
    secular_age: 540.0e6
    uncertainty: 1.0e7
    label: Precambrian-Cambrian boundary
  - young_age: ice_age_end_age        # 2556 YBP
    secular_age: 11500.0
    uncertainty: 30.0
    label: end of the Ice Age

fixed:                                # linear units, always
  lambda_c: 1.0
  k_c: 0.0
  t_c: 1.0
  t_F: flood_start_date
  t_F2: flood_end_date

priors:                               # in each parameter's sampling space
  lambda_F: {mean: 6.0, sigma: 1.0}   # log-scale, so these are log10
  k_F: {mean: -3.0, sigma: 1.0}

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
instantaneous Flood 1656 years after Creation, Ice Age ending at 3500). Fields
are those of [`Chronology`](api/chronology.md). Whatever you set here governs
the whole fit, including the `present_time` that forward ages are measured
against.

### `constraints`

A list of matched date pairs. `young_age` is an **AGE** — years before present;
`uncertainty` is the standard deviation on `secular_age`, in years; `label` is
optional and appears in printed output. At least one is required, and `card
calibrate` needs exactly two.

### `fixed`

Parameters pinned to a value, in **linear** units regardless of how the
parameter is sampled. Anything not listed here (and not structurally
un-fittable, like `lambda_bg`) is free.

### `priors`

Gaussian priors, in each parameter's **sampling space** — log10 for the
log-scale parameters (`lambda_c`, `lambda_F`, `k_c`, `k_F`), linear for the
times. Omitted parameters fall back to the spec's defaults.

### `sampler`

`n_walkers`, `n_steps`, `burn_in`, `seed`, `init_spread`, `progress`, and
`initial_guess`.

`initial_guess` is where the walkers start, in sampling space. It is either a
mapping of free-parameter names to values, or the string `calibrate`, which
solves the config's two constraints exactly with
[`solve_flood_only`](api/calibrate.md) and starts there.

!!! danger "Use it"

    This posterior has a second, far local maximum that traps walkers
    permanently. Started from the prior means, about a quarter of them fall in
    during burn-in and contaminate every percentile. `initial_guess: calibrate`
    is the cure; see [tutorial 2](tutorials/fitting.md#start-the-walkers-at-the-answer).

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
    "fixed": {"lambda_c": 1.0, "k_c": 0.0, "t_c": 1.0,
              "t_F": "flood_start_date", "t_F2": "flood_end_date"},
})
print(config.constraints[0].young_age, config.fixed_params["t_F"])
```

```text
4400.0 1656.0
```

`RunConfig.from_file` loads YAML or JSON; `build_fitter()` returns the
configured [`MCMCFitter`](api/inference.md); `calibrated_start()` runs the
deterministic solve.
