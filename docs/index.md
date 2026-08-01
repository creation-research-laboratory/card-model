# CARD

**C**alibrating **A**ccelerated **R**adiometric **D**ecay: a model of
time-varying radiometric decay rates within a young-earth creation framework,
and the code that fits it to data.

CARD converts between the "true" young-earth age of a rock and the "secular"
age it would appear to have, given a decay rate \(\lambda(t)\) that was
accelerated during the Creation week and the Flood and has relaxed back toward
today's rate since. Model parameters can be **specified**, **solved** exactly
from matched date pairs, or **sampled** with MCMC when the dates carry
uncertainties.

<div class="grid cards" markdown>

-   :material-function-variant: **[The model](model.md)**

    The piecewise \(\lambda(t)\), the age integral, and its closed form.

-   :material-school: **[Tutorials](tutorials/forward-inverse.md)**

    Convert ages in both directions, then fit the model to two dated events.

-   :material-console: **[Run configs and CLI](cli.md)**

    Describe a whole fit in a YAML file and run it with `card fit`.

-   :material-api: **[API reference](api/models.md)**

    Every public class and function, generated from the source.

</div>

## Installation

=== "From PyPI"

    ```bash
    pip install card-model
    ```

    Or pin a version:

    ```bash
    pip install "card-model==0.1.0"
    ```

=== "From source"

    ```bash
    git clone https://github.com/creation-research-laboratory/card-model.git
    cd card-model
    python3 -m venv .venv && source .venv/bin/activate
    pip install -e ".[dev,docs]"
    ```

    The `dev` extra adds pytest; `docs` adds the tooling for this site and for
    rendering the Quarto paper.

Python 3.10 or newer. The package installs `numpy`, `scipy`, `matplotlib`,
`emcee`, `corner`, `h5py` and `pyyaml`; `import card` itself pulls in none of
them, resolving each name on first use, so a headless or browser-side build can
use the models without a plotting stack.

## Quickstart

```python
from card import GeneralModel, FLOOD_AGE

# The flood-only limit: no Creation-week acceleration, instantaneous Flood.
model = GeneralModel.flood_only(lambda_F=3.2e6, k_F=6e-3)

# A rock formed at the Flood appears this old to a secular clock:
print(f"{model.forward_age(FLOOD_AGE):.4g} years")

# And the young age of a rock dated to 65 Myr:
print(f"{model.inverse_age(65e6):.0f} years before present")
```

```text
5.333e+08 years
4049 years before present
```

Fitting that model to dated events is the subject of
[tutorial 2](tutorials/fitting.md); the short version is that two matched date
pairs determine both parameters exactly:

```python
from card import solve_flood_only, FLOOD_AGE, ICE_AGE_END_AGE

result = solve_flood_only(
    flood_age=FLOOD_AGE,            flood_secular_age=541e6,
    second_age=ICE_AGE_END_AGE,     second_secular_age=11.7e3,
)
print(f"lambda_F = {result.lambda_F:,.0f}, k_F = {result.k_F:.4g}")
```

```text
lambda_F = 3,223,698, k_F = 0.005959
```

## Ages and dates

One convention runs through the whole package, and getting it wrong is the
single easiest way to produce a plausible wrong answer:

| Suffix | Counts | Direction | Examples |
| --- | --- | --- | --- |
| `*_DATE` | years **after** Day 1 of Creation | forward | `t_c`, `t_F`, `t_F2`, `FLOOD_START_DATE` |
| `*_AGE` | years **before present** (YBP) | backward | every argument of `forward_age`/`inverse_age`, `FLOOD_AGE` |

A DATE and its matching AGE sum to the age of the Earth. `lambda_func(t)` takes
a DATE; ages in and out of the model are AGEs. See
[the model](model.md#time-conventions) for the rule and
[`card.chronology`](api/chronology.md) for the conversions.

## The paper

The mathematical write-up lives in `docs/paper/CARD_model.qmd` (Quarto). It
imports this package for every date, figure and solved parameter, so the paper
and the code cannot drift apart. Render it with:

```bash
quarto render docs/paper/CARD_model.qmd
```

## License and citation

CARD is released under the Apache-2.0 license. If you use it in published work,
cite it with the metadata in `CITATION.cff` — GitHub renders a ready-made
citation from it under *Cite this repository*.
