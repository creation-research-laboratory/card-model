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

## Background, Motivation, and Context

Radiometric dating estimates the age of a rock from the ratio of a radioactive
parent isotope to the products it decays into, on the assumption that the decay
rate has been constant since the rock formed. On that assumption the Earth is
about 4.5 billion years old, the Precambrian–Cambrian boundary falls near 541
million years ago, and the last glacial period ended roughly 11,700 years ago.
Those dates, and the constant-rate assumption underlying them, are the standard
framework of modern geochronology.

Young-earth creation models instead place the age of the Earth at roughly six to ten
thousand years, which cannot be reconciled with those dates unless something in
the standard assumptions differs. One long-standing proposal is that the decay
rates were not in fact constant — that decay was dramatically accelerated
during one or more episodes in the past, so that a great deal of decay occurred
in a short time and rocks consequently *appear* far older than they are. That
hypothesis was investigated in detail by the RATE project (Radioisotopes and
the Age of The Earth, 1997–2005), which examined helium retention in zircons,
radiohalos, fission tracks and isotopic discordance. RATE found evidence of accelerated decay, but they did not propose a specific model for how it worked. 

Neither RATE nor any other creationist researchers have provided a general quantitative mapping. If decay was 
accelerated, then by how much, beginning when, and with what time dependence —
and what young-earth age corresponds to a particular published date? CARD is an
attempt to provide a framework for answering that question that allows for flexibility in testing various models while also providing for a form that can be calculated rather than asserted.
It represents the decay rate as an explicit function of time, λ(t), with a
small number of parameters: when acceleration occurred, how intense it
was, and how quickly it relaxed back to the rate we measure today. Integrating
that function gives the apparent age a rock of any true age would present to a
conventional analysis; inverting it goes the other way. Parameters are not
assumed, they are **calibrated** from matched date pairs, events assigned both
a young-earth date and a conventional one, and then either solved exactly or fitted with uncertainties.
This framework allows different young-earth age models to be tested against their implications for other processes, such as sediment flux rates during the Flood, the timing and rate of ocean spreading, and correcting the ocean temperature record to a young-age framework. 

Making the model explicit is the point. Any set of assumptions can be tested, varied, disagreed with, and tested: how much does the answer depend on where the Flood is placed in the rock record? At what point does the decay rate return to the background value? Different assumptions produce different numbers, and the framework makes that dependence visible instead of hiding it.

CARD is a modeling tool, not an argument. It takes a young-earth chronology as
an input assumption and works out the consequences; it does not attempt to
establish that chronology, and it does not address the physical objections to
accelerated decay, such as the the heat problem, which the RATE researchers themselves identified as unresolved. Those questions are not addressed by this model. However what we do hope we have provided is a tool that other creation researchers can use to test hypotheses and assess their own model predictions, with the goal of advancing scientific understanding of the creation model. 

## Install

```bash
pip install card-model
```

Or from source, for development:

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
card init myrun.yaml         # a documented starter config, ready to edit
card calibrate myrun.yaml    # solve its two constraints exactly, in milliseconds
card fit myrun.yaml          # the full MCMC: chain, figures, summary
```

## Ages and dates

One convention runs through the package: a name ending in `_DATE` counts years
**after** Day 1 of Creation, and one ending in `_AGE` counts years **before
present**. A matching pair sums to the age of the Earth. Model parameters
(`t_c`, `t_F`, `t_F2`) are DATEs; everything into or out of `forward_age` and
`inverse_age` is an AGE.

## The paper

[`docs/paper/CARD_model.qmd`](https://github.com/creation-research-laboratory/card-model/blob/main/docs/paper/CARD_model.qmd)
is the mathematical write-up. It imports this package for every date, figure
and solved parameter, so the paper and the code cannot drift apart.

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

Apache-2.0 — see
[`LICENSE`](https://github.com/creation-research-laboratory/card-model/blob/main/LICENSE).
If you use CARD in published work, cite it with the metadata in
[`CITATION.cff`](https://github.com/creation-research-laboratory/card-model/blob/main/CITATION.cff)
(GitHub renders a ready-made citation under *Cite this repository*).
