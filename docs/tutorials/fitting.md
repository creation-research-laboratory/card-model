# Tutorial 2 — Fitting the model to dates

A **matched date pair** is one event dated two ways: a young AGE (years before
present) and the secular age rock formed then would appear to have. Each pair
is one equation, so two pairs determine the two free parameters of the
flood-only model.

There are two ways to use them, and they answer different questions:

| | [`card.calibrate`](../api/calibrate.md) | [`card.inference`](../api/inference.md) |
| --- | --- | --- |
| Question | What parameters honor these dates exactly? | What parameters are *consistent* with these dates? |
| Input | Dates | Dates **and their uncertainties** |
| Output | One answer | A posterior distribution |
| Cost | Milliseconds | Seconds to minutes |

Start with the exact solve. It is fast, needs no tuning, and — as the last
section shows — the MCMC needs it anyway.

## Two dates, solved exactly

The standard pair of constraints: rocks formed at the Flood appear
Precambrian-Cambrian (~541 Myr), and rocks from the end of the Ice Age appear
~11.7 kyr old.

```python
from card import solve_flood_only, FLOOD_AGE, ICE_AGE_END_AGE

result = solve_flood_only(
    flood_age=FLOOD_AGE,           flood_secular_age=541e6,
    second_age=ICE_AGE_END_AGE,    second_secular_age=11.7e3,
)

print(f"lambda_F = {result.lambda_F:,.0f} x background")
print(f"k_F      = {result.k_F:.6g} / year")
print(f"largest relative residual: {result.max_abs_residual:.1e}")
```

```text
lambda_F = 3,223,698 x background
k_F      = 0.00595882 / year
largest relative residual: 2.0e-15
```

Both constraints are honored to machine precision, which is what "solved"
rather than "fitted" means: two equations, two unknowns. The result carries the
built model, ready to use:

```python
model = result.model
print(f"{model.forward_age(FLOOD_AGE):,.0f}")
print(f"{model.inverse_age(65e6):,.0f} YBP")
```

```text
541,000,000
4,044 YBP
```

!!! tip "One pair, one unknown"

    With \(k_F\) known from elsewhere, a single pair determines \(\lambda_F\):
    `solve_lambda_F(flood_age=..., flood_secular_age=..., k_F=...)`. The
    secular age is strictly increasing in \(\lambda_F\), so the root is unique
    and bisection finds it with no initial guess.

Both solves are bracketed root-finds, deliberately. An earlier 2-D `fsolve`
version needed a hand-tuned starting guess and silently wandered to
\(\lambda_F \approx 10^{-8}\) on chronologies the guess did not suit.

## The same dates, with uncertainties

When the dates carry uncertainties, the question changes from *what fits* to
*what is consistent*, and the answer is a posterior. `MCMCFitter` takes
`(young_age, secular_age, uncertainty)` triples:

```python
from card import MCMCFitter, FLOOD_START_DATE, FLOOD_END_DATE

data = [
    (FLOOD_AGE,        541e6,   1e7),    # +/- 10 Myr
    (ICE_AGE_END_AGE,  11.7e3,  100.0),  # +/- 100 yr
]

fitter = MCMCFitter(
    data,
    # Pin everything but lambda_F and k_F: the flood-only limit.  Fixed values
    # are always linear, whatever space the parameter is sampled in.
    fixed_params={'lambda_c': 1.0, 'k_c': 0.0, 't_c': 1.0,
                  't_F': FLOOD_START_DATE, 't_F2': FLOOD_END_DATE},
    # lambda_F and k_F are log-scale parameters, so their priors are log10.
    prior_means={'lambda_F': 6.5, 'k_F': -2.2},
    prior_sigmas={'lambda_F': 1.0, 'k_F': 1.0},
)
print(fitter.free_param_names, fitter.ndim)
```

```text
('lambda_F', 'k_F') 2
```

Which parameters are free, whether each is sampled in log10, and the default
priors all come from the [parameter spec](../api/parameters.md) — there is no
list of parameter names inside the fitter to fall out of date.

### Start the walkers at the answer

Now the part that matters. **Do not start this fit at the prior means.**

```python
import numpy as np

exact = solve_flood_only(FLOOD_AGE, 541e6, ICE_AGE_END_AGE, 11.7e3)
initial_guess = [np.log10(exact.lambda_F), np.log10(exact.k_F)]

np.random.seed(0)
results = fitter.run_mcmc(n_walkers=16, n_steps=400, burn_in=100,
                          initial_guess=initial_guess, progress=False)

print(f"stuck walkers:        {len(results['stuck_walkers'])}")
print(f"acceptance fraction:  {results['acceptance_fraction']:.2f}")
```

```text
stuck walkers:        0
acceptance fraction:  0.71
```

This posterior is bimodal. Besides the real solution there is a local maximum
at tiny \(\lambda_F\) with a \(k_F\) small enough that the rate never relaxes:
it fits the tight Ice Age constraint while missing the Flood by ~50\(\sigma\).
Started from the prior means, roughly a quarter of the walkers fall into it
during burn-in and **can never leave** — the barrier between the modes is
around \(10^{10}\) in log-posterior, so no proposal landing between them is
ever accepted. The run still looks plausible: the median comes out right while
the 68% interval runs from 5.4 to 3.3 million.

`MCMCFitter` reports this rather than letting it pass. Any walker whose median
log-posterior sits 50 or more below the best is listed in
`results['stuck_walkers']` and warned about; nothing is ever discarded for you.

!!! danger "Rule of thumb"

    If `stuck_walkers` is non-empty, the percentiles are contaminated —
    re-run from a better starting point rather than reasoning about the
    numbers. `solve_flood_only` gives that starting point exactly, for free.

### Read the posterior

`summarize_mcmc` reports every parameter in **both** spaces, because
`lambda_F` is sampled in log10 and the model wants the linear value:

```python
from card import summarize_mcmc

summary = summarize_mcmc(results['samples'], results['param_names'],
                         log_scale=results['log_scale'])
for row in summary:
    print(f"{row['parameter']:>9}: {row['linear_median']:.6g} "
          f"[{row['linear_16%']:.6g}, {row['linear_84%']:.6g}]")
```

```text
 lambda_F: 3.21882e+06 [3.14805e+06, 3.28596e+06]
      k_F: 0.00595822 [0.00594554, 0.00597094]
```

Use the `linear_*` keys whenever you feed a posterior back into a model. The
`median`/`mean` keys are the *sampled* values, so for a log-scale parameter
they are around 6.5, not 3.2 million — a mistake the main driver script once
made, plotting a `lambda_F` of 6.5.

The posterior is centered on the exact solve, as it should be: the extra
information in the MCMC is the width, not the location.

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
(400, 16, 2) ['lambda_F', 'k_F']
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

The corner plot of a converged run shows one tight, strongly correlated ridge:
\(\lambda_F\) and \(k_F\) trade off against each other, since a faster
relaxation can be compensated by a higher peak rate.

## Doing this without Python

Everything above is one YAML file and one command — see
[run configs and CLI](../cli.md):

```bash
card calibrate examples/flood_only.yaml   # the exact solve
card fit examples/flood_only.yaml         # the full MCMC, figures included
```
