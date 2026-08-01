# The model

## The decay rate

CARD does not model the decay of any particular isotope. It models the
**decay rate itself** as a function of time, normalized by the rate measured
today, on the assumption that every isotope is affected in the same proportion.
The rate is piecewise: constant during each accelerated period, relaxing
exponentially back toward the background rate after it.

\[
\lambda(t) = \begin{cases}
\lambda_c & 0 < t \le t_c \\
\left(\lambda_c - \lambda_{bg}\right) e^{-k_c (t - t_c)} + \lambda_{bg} & t_c < t \le t_{F} \\
\lambda_F & t_{F} < t \le t_{F2} \\
\left(\lambda_F - \lambda_{bg}\right) e^{-k_F (t - t_{F2})} + \lambda_{bg} & t_{F2} < t
\end{cases}
\]

Here \(t\) is a **DATE** — years after Day 1 of Creation. The exponentials are
anchored at the end of each accelerated period, so \(\lambda\) is at its peak
when the period ends and decays from there.

## The parameters

| Name | Symbol | Unit | Meaning |
| --- | --- | --- | --- |
| `lambda_c` | \(\lambda_c\) | — | Decay rate during the Creation week, as a multiple of background |
| `lambda_F` | \(\lambda_F\) | — | Decay rate during the Flood, as a multiple of background |
| `lambda_bg` | \(\lambda_{bg}\) | — | Background rate; **always 1** by normalization, and not fittable |
| `k_c` | \(k_c\) | 1/year | Post-Creation relaxation constant |
| `k_F` | \(k_F\) | 1/year | Post-Flood relaxation constant |
| `t_c` | \(t_c\) | DATE | When the Creation week ends |
| `t_F` | \(t_F\) | DATE | When the Flood starts |
| `t_F2` | \(t_{F2}\) | DATE | When the Flood ends |

Each parameter is declared exactly once, as a
[`ParamSpec`](api/parameters.md) on its dataclass field, carrying its symbol,
unit, bounds, description and whether it is sampled logarithmically. The
fitter, the plots and any GUI read that declaration instead of keeping their
own copies. `card schema` prints the live version as JSON Schema.

`GeneralModelParams` validates on construction, so a constructed instance is
always usable:

- every \(\lambda \ge 1\) — rates are multiples of the background rate, and the
  model describes decay that is *accelerated*, never slower than today's;
- \(k_c, k_F \ge 0\) — the minus sign is already in \(e^{-k\,\Delta t}\), so a
  positive \(k\) is what decays and \(k = 0\) is the no-relaxation limit;
- dates ordered \(t_c \le t_F \le t_{F2}\), with \(t_F = t_{F2}\) the
  instantaneous-Flood limit;
- a warning past a two-year Flood, and `lambda_bg != 1` rescaled to 1 rather
  than rejected.

## From decay rate to apparent age

Radiometric decay obeys \(dN/dt = -\lambda(t) N\), so a rock formed at DATE
\(t_f\) and measured at the present \(t_p\) retains

\[
\frac{N}{N_0} = \exp\left(-\int_{t_f}^{t_p} \lambda(t')\,dt'\right).
\]

A secular analysis reads that same ratio assuming \(\lambda = \lambda_{bg}\)
throughout, which gives an apparent age

\[
A_{sec} = \int_{t_f}^{t_p} \frac{\lambda(t')}{\lambda_{bg}}\,dt'.
\]

That integral is `forward_age`; inverting it for \(t_f\) is `inverse_age`.
Every region of \(\lambda\) is constant or a decaying exponential, so
`GeneralModel` evaluates the integral in **closed form** rather than by
quadrature, and the inverse is a bracketed `brentq` solve on
\([0, t_p]\).

!!! note "Why not quadrature"

    An earlier version integrated numerically without telling the quadrature
    where \(\lambda\) jumps. Relative errors reached \(8\times10^{-3}\), enough
    to make `forward_age` **non-monotone** near the Flood, which in turn made
    the old `fsolve` inverse fail on up to 17% of targets. The closed form is
    also ~80x faster, which matters inside an MCMC loop.

### The flood-only limit

Setting \(\lambda_c = \lambda_{bg}\) (no Creation-week acceleration) and
\(t_F = t_{F2}\) (an instantaneous Flood) leaves two parameters, and the
integral collapses to a form worth knowing by heart. Writing
\(R = (\lambda_F - \lambda_{bg})/\lambda_{bg}\), \(A_{ya}\) for the young age
of the rock and \(A_F\) for the age of the Flood — both **AGEs**, years before
present:

\[
A_{sec} = A_{ya} + \frac{R}{k_F} e^{-k_F A_F}\left(e^{k_F A_{ya}} - 1\right),
\qquad A_{ya} \le A_F .
\]

For rock that predates the Flood the bracket saturates at
\(1 - e^{-k_F A_F}\): everything older than the Flood picks up the same fixed
excess of apparent age, which is why the model cannot distinguish
Precambrian ages from one another.

Note that the age of the Earth does not appear. What matters is how long ago
the Flood was, because that is where the exponential is anchored.

## Time conventions

Two clocks run in opposite directions, and **the name of a quantity tells you
which one it uses**:

| Suffix | Counts | Zero at | Used for |
| --- | --- | --- | --- |
| `*_DATE` | years after Day 1 of Creation (\(t\)) | Creation | `lambda_func`, `t_c`, `t_F`, `t_F2`, `present_time` |
| `*_AGE` | years before present (\(\tau\), YBP) | now | `forward_age`, `inverse_age`, all fitted data |

\[
\tau = A_E - t, \qquad t = A_E - \tau
\]

where \(A_E\) is the age of the Earth — which is numerically also the DATE of
the present.

!!! danger "This rule exists because it was once broken"

    `FLOOD_AGE` (years before present) and `ICE_AGE_END_AGE` (then years after
    Creation) shared a suffix while meaning opposite things. A whole MCMC run
    was fitted with the Ice Age at 3500 YBP instead of 2556, and nothing
    complained. `tests/test_chronology.py` now pins the DATE + AGE = age of the
    Earth relationships so a refactor cannot silently flip one.

## Chronology

The dates of Creation, the Flood and the Ice Age are **user-specifiable
modeling assumptions, not constants**. They live in a frozen
[`Chronology`](api/chronology.md) dataclass that derives the matching AGEs and
loads and saves JSON:

```python
from card import Chronology, DEFAULT_CHRONOLOGY

print(DEFAULT_CHRONOLOGY.age_of_earth)       # 6056.0
print(DEFAULT_CHRONOLOGY.flood_start_date)   # 1656.0  (a DATE)
print(DEFAULT_CHRONOLOGY.flood_start_age)    # 4400.0  (the matching AGE)

alternative = Chronology(age_of_earth=6600.0, flood_start_date=1600.0,
                         flood_end_date=1600.0, ice_age_end_date=3600.0)
print(alternative.flood_start_age)           # 5000.0
```

`DEFAULT_CHRONOLOGY` backs the convenience constants in
[`card.constants`](api/constants.md) (`AGE_OF_EARTH`, `FLOOD_START_DATE`,
`FLOOD_AGE`, `ICE_AGE_END_AGE`, …). Anything configurable should take a
`Chronology` rather than reading those.

## Error contract

Every model raises `ValueError` on invalid input. There are no NaN sentinels
and no plausible-looking numbers returned for nonsense:

- ages must be finite, \(\ge 0\), and no greater than `present_time`
  (a larger age would place formation before Creation);
- `inverse_age` additionally rejects secular ages above `max_secular_age()`,
  which is the oldest apparent age the model can produce;
- `compute_integral` always returns the **normalized** integral of
  \(\lambda/\lambda_{bg}\).

The narrowness matters downstream: `MCMCFitter.log_likelihood` catches
`ValueError` specifically and returns \(-\infty\), which is how parameter
bounds reach the sampler. Any other exception is a bug and is allowed to
surface.
