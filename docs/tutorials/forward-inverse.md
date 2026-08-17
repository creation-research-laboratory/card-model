# Tutorial 1 — Forward and inverse ages

This tutorial builds a model, converts ages in both directions, and shows what
the model refuses to do. Every code block runs as written; they share state, so
run them in order.

## Build a model

The full model takes eight parameters, which travel together in a validated
`GeneralModelParams`:

```python
from card import GeneralModel, GeneralModelParams, FLOOD_START_DATE

params = GeneralModelParams(
    lambda_c=1e3,               # Creation-week rate, x background
    lambda_F=1e5,               # Flood rate, x background
    lambda_bg=1.0,              # background: always 1 by normalization
    k_c=1e-1,                   # post-Creation relaxation, 1/year
    k_F=0.0,                    # in-Flood relaxation, 1/year (0 = constant)
    k_PF=1e-2,                  # post-Flood relaxation, 1/year
    t_c=1.0,                    # DATE the Creation week ends
    t_F=FLOOD_START_DATE,       # DATE the Flood starts  (1656)
)
model = GeneralModel(params)
```

`t_F2` is absent because it is derived: the Flood runs for a year, so it is
`t_F + 1`. So is `lambda_F2`, the rate at the Flood's end, which continuity
pins to whatever `k_F` has brought `lambda_F` down to by then — here `k_F` is
0, so the rate never falls and `lambda_F2` is just `lambda_F`:

```python
print(params.t_F2, params.lambda_F2)
```

```text

1657.0 100000.0
```

Most work uses the **flood-only limit** — no Creation-week acceleration, so
the Flood is the only accelerated phase — which has a factory of its own:

```python
model = GeneralModel.flood_only(lambda_F=3.2e6, k_PF=6e-3)
```

That leaves the rate constant across the Flood year (`k_F` defaults to 0);
pass `k_F=` to let it relax across the Flood as well.

`GeneralModelParams.defaults()` is a third route, filling in each parameter's
declared default and applying any overrides you name:

```python
defaults = GeneralModelParams.defaults(lambda_F=5e5, k_PF=8e-3)
print(defaults.lambda_c, defaults.t_F)
```

```text

1.0 1656.0
```

## Forward: young age → secular age

`forward_age` takes an **AGE** — years before present — and returns the age a
secular analysis would report:

```python
from card import FLOOD_AGE, ICE_AGE_END_AGE

for age in (0.0, 1000.0, ICE_AGE_END_AGE, FLOOD_AGE):
    print(f"{age:>7,.0f} YBP -> {model.forward_age(age):>14,.0f} secular years")
```

```text

      0 YBP ->              0 secular years
  1,000 YBP ->          1,001 secular years
  2,556 YBP ->         10,962 secular years
  4,400 YBP ->    536,537,566 secular years
```

Two things are visible in those numbers. Recent rock is barely affected: the
decay rate has long since relaxed, so 1000 YBP looks like 1001 years. And the
Flood is a cliff — 1844 years further back multiplies the apparent age by more
than four orders of magnitude.

The oldest apparent age the model can produce is the secular age of rock formed
on Day 1:

```python
print(f"{model.max_secular_age():,.0f} years")
```

```text

536,539,222 years
```

Everything formed before the Flood lands within 0.001% of that value, because
the accelerated decay is anchored at the Flood and cannot distinguish what came
before it.

## Inverse: secular age → young age

`inverse_age` runs the conversion the other way, which is the question most
often asked of the model — *what young age corresponds to this published
date?*

```python
for secular in (65e6, 250e6, 500e6):
    print(f"{secular:>12,.0f} secular years -> "
          f"{model.inverse_age(secular):>6,.0f} YBP")
```

```text

  65,000,000 secular years ->  4,048 YBP
 250,000,000 secular years ->  4,273 YBP
 500,000,000 secular years ->  4,388 YBP
```

The round trip is exact to numerical precision, which the test suite pins
densely:

```python
young = model.inverse_age(65e6)
print(f"{model.forward_age(young):,.1f}")
```

```text

65,000,000.0
```

## What the model refuses

Invalid input raises `ValueError` — never a NaN, never a plausible number:

```python
try:
    model.inverse_age(1e12)          # older than the model can produce
except ValueError as error:
    print(error)
```

```text

secular_age (1e+12) exceeds the maximum this model can produce (5.36539e+08, for a rock formed on Day 1 of Creation).  No true age exists in [0, 6056].
```

The same applies to an age before Creation (`forward_age(7000)`), a negative
age, and a `lambda_F` below the background rate. That last one is checked at
construction, so an invalid model cannot be built in the first place:

```python
try:
    GeneralModel.flood_only(lambda_F=0.5, k_PF=1e-2)
except ValueError as error:
    print(error)
```

```text

lambda_F (0.5) must be >= 1.  Decay rates are normalized to the background rate, so a value below 1 would mean decay slower than the present day, which the model does not describe.
```

## Under a different chronology

The age of the Earth is not baked in. Pass `present_time` to work under another
chronology, and use that chronology's own conversions to get the ages:

```python
from card import Chronology

alt = Chronology(age_of_earth=6600.0, flood_start_date=1600.0,
                 flood_end_date=1601.0, ice_age_end_date=3600.0)
alt_model = GeneralModel.flood_only(lambda_F=3.2e6, k_PF=6e-3,
                                    t_F=alt.flood_start_date,
                                    t_F2=alt.flood_end_date)

print(f"Flood at {alt.flood_start_age:,.0f} YBP -> "
      f"{alt_model.forward_age(alt.flood_start_age, alt.present_date):,.0f}")
```

```text

Flood at 5,000 YBP -> 536,538,166
```

## Plot it

The plotting helpers all accept an optional `ax`, so they draw into a figure
you own when you have one and manage their own when you do not:

```python
from card import plot_age_comparison, plot_lambda_history

plot_lambda_history(model, out_file="lambda_history.png")
plot_age_comparison(lambda_F=3.2e6, k_PF=6e-3, out_file="age_comparison.png")
```

`plot_lambda_history` plots \(\lambda\) against a **DATE**; the age-curve
figures plot against an **AGE**. It is the one place in the package where the
x axis runs the other way, and the axis label says so.

## Next

[Tutorial 2](fitting.md) fits the two flood-only parameters to dated events —
exactly with `card.calibrate`, and with uncertainties using MCMC.
