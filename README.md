# CARD

[![tests](https://github.com/creation-research-laboratory/card-model/actions/workflows/tests.yml/badge.svg)](https://github.com/creation-research-laboratory/card-model/actions/workflows/tests.yml)
[![docs](https://github.com/creation-research-laboratory/card-model/actions/workflows/docs.yml/badge.svg)](https://creation-research-laboratory.github.io/card-model/)

**C**alibrating **A**ccelerated **R**adiometric **D**ecay — a model of
time-varying radiometric decay rates within a young-earth creation framework,
and the code that fits it to data.

CARD converts between the "true" young-earth age of a rock and the "secular"
age it would appear to have, given a decay rate that was accelerated during the
Creation week and the Flood and has relaxed back toward today's rate since.
Parameters can be specified, solved exactly from matched date pairs, or sampled
with MCMC when the dates carry uncertainties.

📖 **[Documentation](https://creation-research-laboratory.github.io/card-model/)** —
[the model](https://creation-research-laboratory.github.io/card-model/model/) ·
[tutorials](https://creation-research-laboratory.github.io/card-model/tutorials/forward-inverse/) ·
[run configs and CLI](https://creation-research-laboratory.github.io/card-model/cli/) ·
[API reference](https://creation-research-laboratory.github.io/card-model/api/models/) ·
[figure gallery](https://creation-research-laboratory.github.io/card-model/gallery/)

## Install

> **Note**
> CARD is not on PyPI yet. The `pip install card-model` form below is the
> intended interface, written here so it is ready at the first release; until
> then, install from source.

```bash
pip install card-model            # planned, not yet published
```

```bash
git clone https://github.com/creation-research-laboratory/card-model.git
cd card-model
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,docs]"
```

Python 3.10+.

## Quickstart

```python
from card import GeneralModel, FLOOD_AGE

model = GeneralModel.flood_only(lambda_F=3.2e6, k_F=6e-3)

model.forward_age(FLOOD_AGE)   # 533337566.7  — how old Flood rock looks
model.inverse_age(65e6)        # 4049.2       — the young age of a "65 Myr" rock
```

Fitting the model to two dated events, exactly or with uncertainties, is
[tutorial 2](https://creation-research-laboratory.github.io/card-model/tutorials/fitting/).
A whole fit can also be described in a YAML file and run from the command line:

```bash
card fit examples/flood_only.yaml         # MCMC: chain, figures, summary
card calibrate examples/flood_only.yaml   # the same constraints, solved exactly
```

## Ages and dates

One convention runs through the package: a name ending in `_DATE` counts years
**after** Day 1 of Creation, and one ending in `_AGE` counts years **before
present**. A matching pair sums to the age of the Earth. Model parameters
(`t_c`, `t_F`, `t_F2`) are DATEs; everything into or out of `forward_age` and
`inverse_age` is an AGE.

## The paper

`docs/paper/CARD_model.qmd` is the mathematical write-up. It imports this
package for every date, figure and solved parameter, so the paper and the code
cannot drift apart.

```bash
quarto render docs/paper/CARD_model.qmd
```

## Development

```bash
python -m pytest                  # the test suite (a few seconds)
mkdocs serve                      # preview the docs at localhost:8000
python docs/generate_figures.py   # regenerate the gallery figures
```

CI runs the suite on Ubuntu and macOS across Python 3.10–3.14, and publishes
the documentation from `main`.

## License and citation

See [`LICENSE`](LICENSE). A `CITATION.cff` will accompany the first tagged
release.
