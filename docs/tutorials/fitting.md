# Tutorial 2 — Fitting the model to dates

A **matched date pair** is one event dated two ways: a young AGE (years before
present) and the secular age rock formed then would appear to have. Each pair
is one equation, so the number of pairs you need is the number of unknown
rates.

The Flood carries three of them:

| | Symbol | Meaning |
| --- | --- | --- |
| Peak | \(\lambda_F\) | The rate at the Flood's onset |
| In-Flood | \(k_F\) | How fast it relaxes *during* the Flood year |
| Post-Flood | \(k_{PF}\) | How fast it relaxes *after* it |

Three unknowns, so **three pairs**. Two are not enough, which is why
`solve_flood_only` asks you to supply \(k_F\) rather than solving for it.

There are two ways to use the pairs, and they answer different questions:

| | [`card.calibrate`](../api/calibrate.md) | [`card.inference`](../api/inference.md) |
| --- | --- | --- |
| Question | What parameters honor these dates exactly? | What parameters are *consistent* with these dates? |
| Input | Dates | Dates **and their uncertainties** |
| Output | One answer | A posterior distribution |
| Cost | Milliseconds | Seconds to minutes |

Start with the exact solve. It is fast, needs no tuning, and — as the last
section shows — the MCMC needs it anyway.

## The three anchors

This tutorial uses the Masoretic chronology with the K/Pg boundary as the
post-Flood contact. Under that chronology the Flood is one year long, and its
two ends are two different anchors:

| Event | AGE | Appears to be |
| --- | --- | --- |
| Flood onset | 4400 YBP | Precambrian-Cambrian, 541 Ma |
| Flood end | 4399 YBP | K/Pg, 66 Ma |
| End of the Ice Age | 2556 YBP | 11.5 kyr |

The middle row is what the older two-pair fit could not use. A Flood whose rate
is *constant* across the year has no way to separate its two ends far enough
apart. Anchor such a Flood on the onset and ask what its last day looks like:

```python
from card import solve_flood_only, FLOOD_AGE, FLOOD_END_AGE, ICE_AGE_END_AGE

# k_F=0 is the old constant-rate Flood, and is still the default.
flat = solve_flood_only(FLOOD_AGE, 541e6, ICE_AGE_END_AGE, 11.5e3, k_F=0.0)
onset = flat.model.forward_age(FLOOD_AGE)
end = flat.model.forward_age(FLOOD_END_AGE)

print(f"Flood onset appears         {onset:13,.0f}")
print(f"Flood end appears           {end:13,.0f}")
print(f"separation across the year  {onset - end:13,.0f}")
print(f"K/Pg would need             {541e6 - 66e6:13,.0f}")
```

```text
Flood onset appears           541,000,000
Flood end appears             537,788,981
separation across the year      3,211,019
K/Pg would need               475,000,000
```

A constant rate does move the apparent age across the Flood year — by about
3.2 Myr — but the K/Pg anchor asks for 475 Myr, roughly 150 times more. No
choice of \(\lambda_F\) fixes that, because raising it pushes *both* ends up
together. Letting \(\lambda\) relax at \(k_F\) as the Flood runs is exactly the
freedom that pulls the two ends apart.

## Three dates, solved exactly

```python
from card import solve_flood_rate

result = solve_flood_rate(
    pre_flood_secular_age=541e6,   # Flood onset, 4400 YBP -> Precambrian-Cambrian
    post_flood_secular_age=66e6,   # Flood end,   4399 YBP -> K/Pg
    ice_age_secular_age=11.5e3,    # Ice Age end, 2556 YBP
)

print(f"lambda_F  = {result.lambda_F:.6g} x background   (peak, at the onset)")
print(f"k_F       = {result.k_F:.6g} / year        (relaxation during the Flood)")
print(f"k_PF      = {result.k_PF:.6g} / year     (relaxation after it)")
print(f"lambda_F2 = {result.model.lambda_F2:.6g} x background   (what is left at the end)")
print(f"largest relative residual: {result.max_abs_residual:.1e}")
```

```text
lambda_F  = 4.54332e+09 x background   (peak, at the onset)
k_F       = 9.56421 / year        (relaxation during the Flood)
k_PF      = 0.00483253 / year     (relaxation after it)
lambda_F2 = 318927 x background   (what is left at the end)
largest relative residual: 6.7e-16
```

Read those numbers as a story about one year. The rate starts about
4.5 billion times background, falls by \(e^{-9.56}\) over the Flood — a factor
of about 14,000 — and hands the post-Flood exponential the 319,000 it has left.
From there it relaxes far more slowly, at \(k_{PF} \approx 0.0048\)/year, which
is a half-life of roughly 140 years.

\(\lambda_{F2}\) is not a fitted parameter. It is a read-only property pinned
by continuity at \(t_{F2}\), which is what makes
\(\lambda_{F2} \ge \lambda_{bg}\) automatic rather than something to validate.

All three constraints are honored, not traded off:

```python
from card import FLOOD_AGE, FLOOD_END_AGE, ICE_AGE_END_AGE

model = result.model
anchors = [
    ("Flood onset", FLOOD_AGE,       541e6),
    ("Flood end",   FLOOD_END_AGE,    66e6),
    ("Ice Age end", ICE_AGE_END_AGE, 11.5e3),
]
for label, age, target in anchors:
    print(f"{label:12} {age:6.0f} YBP -> {model.forward_age(age):13,.0f} "
          f"(asked for {target:13,.0f})")
```

```text
Flood onset    4400 YBP ->   541,000,000 (asked for   541,000,000)
Flood end      4399 YBP ->    66,000,000 (asked for    66,000,000)
Ice Age end    2556 YBP ->        11,500 (asked for        11,500)
```

Every residual is at machine precision, which is what "solved" rather than
"fitted" means: three equations, three unknowns.

### Why this needs no initial guess

Three unknowns would normally mean a 3-D root-find and a starting guess to go
with it. This one decouples instead:

1. The **post-Flood** and **Ice Age** pairs both sit at or after \(t_{F2}\),
   where only \(\lambda_{F2}\) and \(k_{PF}\) enter. Those two pairs pin those
   two unknowns on their own — a two-pair solve with the Flood's length set to
   zero, because from the Flood's end onward there is no Flood left to
   integrate.
2. The **pre-Flood** pair then differs from the post-Flood one by the in-Flood
   integral alone, which reduces to a single increasing function of \(k_F\).
   One bracketed root gives \(k_F\), and continuity gives \(\lambda_F\).

So it is a sequence of 1-D bracketed solves, each with a guaranteed sign
change. An earlier `fsolve` version of the two-pair solve needed a hand-tuned
starting guess and silently wandered to \(\lambda_F \approx 10^{-8}\) on
chronologies the guess did not suit; nothing here can do that.

!!! tip "Fewer pairs, fewer unknowns"

    Two pairs still work if you supply \(k_F\) yourself —
    `solve_flood_only(flood_age=..., flood_secular_age=..., second_age=...,
    second_secular_age=..., k_F=...)`, which defaults to `k_F=0` and so
    reproduces the old constant-rate Flood exactly. With \(k_{PF}\) known as
    well, one pair determines \(\lambda_F\): `solve_lambda_F`.

## The same dates, with uncertainties

When the dates carry uncertainties, the question changes from *what fits* to
*what is consistent*, and the answer is a posterior. `MCMCFitter` takes
`(young_age, secular_age, uncertainty)` triples:

```python
from card import MCMCFitter, FLOOD_START_DATE, FLOOD_END_DATE

data = [
    (FLOOD_AGE,       541e6,   1e7),   # +/- 10 Myr
    (FLOOD_END_AGE,    66e6,   1e5),   # +/- 100 kyr
    (ICE_AGE_END_AGE, 11.5e3, 30.0),   # +/- 30 yr
]

fitter = MCMCFitter(
    data,
    # Pin the Creation-week parameters and the Flood's two DATEs; leave all
    # three rates free.  Fixed values are always linear, whatever space the
    # parameter is sampled in.
    fixed_params={'lambda_c': 1.0, 'k_c': 0.0, 't_c': 1.0,
                  't_F': FLOOD_START_DATE, 't_F2': FLOOD_END_DATE},
    prior_means={'lambda_F': 9.7, 'k_F': 9.6, 'k_PF': -2.3},
    prior_sigmas={'lambda_F': 1.0, 'k_F': 5.0, 'k_PF': 1.0},
)
print(fitter.free_param_names, fitter.ndim)
```

```text
('lambda_F', 'k_F', 'k_PF') 3
```

Which parameters are free, whether each is sampled in log10, and the default
priors all come from the [parameter spec](../api/parameters.md) — there is no
list of parameter names inside the fitter to fall out of date.

!!! warning "The three rates are not sampled in the same space"

    \(\lambda_F\) and \(k_{PF}\) are sampled in **log10**, so their priors
    above are log10 values: 9.7 means \(5 \times 10^{9}\), and −2.3 means
    0.005. \(k_F\) is sampled **linearly**, so its prior mean of 9.6 means 9.6.

    The reason is the range each one covers. \(\lambda_F\) spans orders of
    magnitude and \(k_{PF}\) is a slow relaxation over millennia, but \(k_F\)
    acts over a single year, so it lives within a few multiples of 1/year — and
    its default of 0 has no log10 at all.

### Start the walkers at the answer

The exact solve is the natural starting point, and it is free. Note that
`initial_guess` is given in **sampling space**, so the log-scale parameters are
passed as log10 and \(k_F\) is passed as-is:

```python
import numpy as np

initial_guess = [np.log10(result.lambda_F), result.k_F, np.log10(result.k_PF)]

# `seed` makes the run reproducible.  It seeds the fitter's own generator, not
# numpy's global one, so two fits in the same process — or in two threads of a
# web app — cannot disturb each other.
results = fitter.run_mcmc(n_walkers=16, n_steps=400, burn_in=100,
                          initial_guess=initial_guess, seed=0, progress=False)

print(f"sampled in log10:     {results['log_scale']}")
print(f"stuck walkers:        {len(results['stuck_walkers'])}")
print(f"acceptance fraction:  {results['acceptance_fraction']:.2f}")
```

```text
sampled in log10:     [True, False, True]
stuck walkers:        0
acceptance fraction:  0.65
```

`results['log_scale']` is the fitter's own record of which space each parameter
was sampled in, in the same order as `param_names` — pass it to anything that
has to interpret the chain.

`MCMCFitter` watches for walkers that have fallen into a far local maximum and
cannot climb out: any walker whose median log-posterior sits 50 or more below
the best is listed in `results['stuck_walkers']` and warned about. Nothing is
ever discarded for you.

!!! danger "Rule of thumb"

    If `stuck_walkers` is non-empty, the percentiles are contaminated —
    re-run from a better starting point rather than reasoning about the
    numbers. The exact solve gives that starting point for free.

    This is not hypothetical. The two-pair flood-only fit against the Flood and
    Ice Age has a second mode at tiny \(\lambda_F\), with a \(k_{PF}\) small
    enough that the rate never relaxes: it fits the tight Ice Age constraint
    while missing the Flood by ~50\(\sigma\). Started from the prior means,
    about a quarter of its walkers fall in during burn-in and can never leave,
    because the barrier between the modes is around \(10^{10}\) in
    log-posterior. The run still looks plausible — the median comes out right
    while the 68% interval runs from 5.4 to 3.3 million.

### Read the posterior

`summarize_mcmc` reports every parameter in **both** spaces, because two of
these three are sampled in log10 and the model wants linear values:

```python
from card import summarize_mcmc

summary = summarize_mcmc(results['samples'], results['param_names'],
                         log_scale=results['log_scale'])
for row in summary:
    print(f"{row['parameter']:>9}: {row['linear_median']:.6g} "
          f"[{row['linear_16%']:.6g}, {row['linear_84%']:.6g}]")
```

```text
 lambda_F: 4.54861e+09 [4.44775e+09, 4.65096e+09]
      k_F: 9.56529 [9.54326, 9.58773]
     k_PF: 0.00483262 [0.0048307, 0.00483448]
```

Use the `linear_*` keys whenever you feed a posterior back into a model. The
`median`/`mean` keys are the *sampled* values, so for a log-scale parameter
they are around 9.66, not 4.5 billion — a mistake the main driver script once
made, plotting a `lambda_F` of 6.5.

The posterior is centered on the exact solve, as it should be: the extra
information in the MCMC is the width, not the location. Note how much tighter
\(k_{PF}\) is than \(\lambda_F\) — the Ice Age pair carries a ±30-year
uncertainty and sits deep in the post-Flood relaxation, so it constrains
\(k_{PF}\) hard, while \(\lambda_F\) answers to the ±10-Myr Precambrian pair.

### Save and reload

Results go to one self-describing HDF5 file that keeps the chain's
`(step, walker)` structure:

```python
from card import load_results, save_results

save_results(results, "chain.h5")
reloaded = load_results("chain.h5")
print(reloaded['chain'].shape, reloaded['param_names'])
```

```text
(400, 16, 3) ['lambda_F', 'k_F', 'k_PF']
```

For a long run, pass `backend_path="chain.h5"` to `run_mcmc` instead: emcee
streams the chain to disk as it goes, so the run is resumable and can be
inspected before it finishes.

### Figures

```python
from card import plot_mcmc_corner, plot_mcmc_traces

plot_mcmc_corner(results['samples'], results['param_names'],
                 log_scale=results['log_scale'], out_file="corner.png")
plot_mcmc_traces(results['chain'], results['log_prob_chain'],
                 results['param_names'], log_scale=results['log_scale'],
                 out_file="traces.png")
```

The corner plot shows where the three rates trade off. \(\lambda_F\) and
\(k_F\) are strongly correlated — both describe the same Flood year, and a
higher peak can be absorbed by relaxing faster — while \(k_{PF}\), pinned by
the Ice Age pair, is nearly independent of the other two.

## Doing this without Python

Everything above is one YAML file and one command — see
[run configs and CLI](../cli.md):

```bash
card init myrun.yaml         # a worked run config to edit
card fit myrun.yaml          # the full MCMC, figures included
card calibrate myrun.yaml    # the exact solve
```

!!! note "`card calibrate` is the two-pair solve"

    `card fit` samples however many constraints the config lists, but
    `card calibrate` requires exactly two and calls `solve_flood_only`. The
    three-pair `solve_flood_rate` shown above is not yet exposed on the command
    line; call it from Python, or use `card fit`.
