"""
Deterministic calibration of the flood-only model from matched date pairs.

A "matched date pair" is one event dated two ways: a young AGE (years before
present) and the secular age the rock would appear to have.  Each pair is one
equation, so:

  * one pair determines one parameter — `solve_lambda_F` fixes k_PF and solves
    for lambda_F;
  * two pairs determine both — `solve_flood_only` solves the 2x2 system so both
    dates are honored exactly;
  * three pairs determine the *in-Flood* relaxation as well —
    `solve_flood_rate` solves the 3x3 system in lambda_F, k_F and k_PF, so a
    pre-Flood contact, a post-Flood contact and a later event are all honored
    at once.

The Flood's length is not among the unknowns anywhere here: it is one year,
taken from the chronology (`Chronology.flood_duration`).  The earlier
`solve_flood_duration`, which inferred a Flood of centuries from three pairs,
is gone with the model that allowed it; `solve_flood_rate` fits the same three
pairs within the Flood year by letting the rate relax across it instead.

This is the deterministic counterpart to `card.inference`.  Use it when the
constraints are exact and you want the answer; use MCMC when the constraints
have uncertainties and you want a posterior.

Extracted from examples/plot_model_calibration.py and its _joint variant, which
each carried their own copy of the solve.

Like `models.py`, this module is standard-library only — the root solve comes
from `card._solvers` rather than scipy — so calibration runs anywhere CPython
does, including a browser under Pyodide.
"""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from ._solvers import brentq
from .chronology import DEFAULT_CHRONOLOGY, Chronology
from .models import GeneralModel, GeneralModelParams

__all__ = [
    "CalibrationResult",
    "solve_flood_rate",
    "solve_flood_only",
    "solve_lambda_F",
]

# Bracket for the log10(lambda_F) search.  10^0 is no acceleration at all and
# 10^12 is far beyond any physically interesting value, so a root in between is
# guaranteed to be found by bisection.
_LOG10_LAMBDA_BRACKET = (0.0, 12.0)


@dataclass(frozen=True)
class CalibrationResult:
    """
    Outcome of a calibration solve.

    Attributes:
        lambda_F: Solved decay rate at the Flood's onset, as a multiple of
            background.
        k_PF: Post-Flood relaxation constant (solved, or the value supplied).
        model: The calibrated model, ready to use.
        flood_date: DATE of the Flood's onset the model was built with.
        residuals: Relative misfit of each constraint, as
            ``predicted / target - 1``.  All entries should be ~1e-12.
        k_F: In-Flood relaxation constant (solved, or the value supplied).
            Zero for the two-pair solves, which hold the rate constant across
            the Flood; only `solve_flood_rate` solves for it.
        flood_duration: Length of the Flood in true years (``t_F2 - t_F``),
            taken from the chronology rather than solved for.
        lambda_F2: Decay rate at the Flood's end — derived from the three above
            by continuity, and the amplitude the post-Flood relaxation starts
            from.
    """

    lambda_F: float
    k_PF: float
    model: GeneralModel
    flood_date: float
    residuals: Tuple[float, ...]
    k_F: float = 0.0
    flood_duration: float = 0.0

    @property
    def lambda_F2(self) -> float:
        """Decay rate at the Flood's end, as a multiple of background."""
        return self.model.lambda_F2

    @property
    def max_abs_residual(self) -> float:
        """Largest absolute relative misfit across all constraints."""
        return max(abs(r) for r in self.residuals) if self.residuals else 0.0


def _flood_date_for(flood_age: float, chronology: Chronology) -> float:
    """Convert a Flood AGE to the DATE the model needs, with a clear error."""
    date = chronology.age_to_date(flood_age)
    if not 0.0 <= date <= chronology.age_of_earth:
        raise ValueError(
            f"flood_age ({flood_age!r}) is outside "
            f"[0, {chronology.age_of_earth}] for this chronology.  It is an "
            "AGE — years before present — not a DATE."
        )
    return date


def _resolve_duration(flood_duration: Optional[float],
                      chronology: Chronology) -> float:
    """The Flood's length: the caller's, or the chronology's year."""
    duration = (chronology.flood_duration if flood_duration is None
                else float(flood_duration))
    if duration < 0.0:
        raise ValueError(
            f"flood_duration ({duration!r}) must be >= 0; it is a length in "
            "true years, not a date."
        )
    return duration


def solve_lambda_F(
    flood_age: float,
    flood_secular_age: float,
    k_PF: float,
    chronology: Chronology = DEFAULT_CHRONOLOGY,
    k_F: float = 0.0,
    flood_duration: Optional[float] = None,
) -> CalibrationResult:
    """
    Solve for lambda_F so one matched date pair is honored, with k_PF given.

    The secular age is strictly increasing in lambda_F at fixed k_PF, so the
    root is unique and bisection finds it without an initial guess.

    Args:
        flood_age: AGE (years before present) at which the Flood *begins*.
        flood_secular_age: Secular age that rock formed at the Flood's onset
            should appear.  The whole Flood year lies between that rock and the
            present, so this constraint sees the in-Flood integral too.
        k_PF: Post-Flood relaxation constant to hold fixed.
        chronology: Chronology used to place the Flood (default: the package's).
        k_F: In-Flood relaxation constant to hold fixed.  The default of 0
            holds the rate constant across the Flood.
        flood_duration: Length of the Flood in true years.  Defaults to the
            chronology's; pass 0.0 to treat it as instantaneous, which is what
            makes this constraint see only the post-Flood relaxation.

    Returns:
        CalibrationResult with the solved lambda_F.

    Raises:
        ValueError: If the target is unreachable for any lambda_F in the search
            bracket, or the inputs are out of range.
    """
    if flood_secular_age <= 0:
        raise ValueError(
            f"flood_secular_age must be positive, got {flood_secular_age!r}"
        )
    flood_date = _flood_date_for(flood_age, chronology)
    duration = _resolve_duration(flood_duration, chronology)

    def build(lambda_F: float) -> GeneralModel:
        return GeneralModel.flood_only(
            lambda_F=lambda_F, k_PF=k_PF, t_F=flood_date,
            t_F2=flood_date + duration, k_F=k_F)

    def residual(log10_lambda_F: float) -> float:
        model = build(10.0 ** log10_lambda_F)
        return model.forward_age(flood_age,
                                 chronology.present_date) - flood_secular_age

    lo, hi = _LOG10_LAMBDA_BRACKET
    if residual(lo) > 0 or residual(hi) < 0:
        raise ValueError(
            f"No lambda_F in [10^{lo:g}, 10^{hi:g}] reproduces a secular age of "
            f"{flood_secular_age:.4g} for a Flood at {flood_age:g} YBP with "
            f"k_PF = {k_PF:g}.  Check the constraint, or widen the bracket."
        )

    lambda_F = 10.0 ** brentq(residual, lo, hi, xtol=1e-12)
    model = build(lambda_F)
    predicted = model.forward_age(flood_age, chronology.present_date)
    return CalibrationResult(
        lambda_F=lambda_F,
        k_PF=k_PF,
        model=model,
        flood_date=flood_date,
        residuals=(predicted / flood_secular_age - 1.0,),
        k_F=k_F,
        flood_duration=duration,
    )


def solve_flood_only(
    flood_age: float,
    flood_secular_age: float,
    second_age: float,
    second_secular_age: float,
    chronology: Chronology = DEFAULT_CHRONOLOGY,
    k_PF_bracket: Tuple[float, float] = (1e-6, 1.0),
    k_F: float = 0.0,
    flood_duration: Optional[float] = None,
) -> CalibrationResult:
    """
    Solve for both lambda_F and k_PF so two matched date pairs are honored.

    Two constraints, two unknowns: the solve is exact rather than a fit, and
    both residuals come back at machine precision.

    The model has a third rate parameter, `k_F`, and two pairs cannot determine
    three unknowns — so `k_F` is an input here, defaulting to 0, a Flood that
    holds lambda at lambda_F for its whole year.  Solve for it instead with
    `solve_flood_rate`, which needs a third pair.

    Implemented as two *nested bracketed* solves rather than a 2-D
    Newton-style solve.  For any candidate k_PF the Flood constraint pins
    lambda_F by a monotone 1-D root (`solve_lambda_F`), which reduces the
    system to a single equation in k_PF alone.  That residual runs from
    positive at small k_PF (the rate barely relaxes, so the second event looks
    far too old) to negative at large k_PF (the rate is back to background
    before the second event), so a sign change is guaranteed and bisection
    always converges.

    The alternative — handing both unknowns to `fsolve` with an initial guess —
    is what the original scripts did, and it silently wandered to
    lambda_F ~ 1e-8 on chronologies whose guess was slightly off.  Bracketing
    removes the guess and the failure mode together.

    Args:
        flood_age: AGE at which the Flood begins.
        flood_secular_age: Secular age rock formed at the Flood's onset should
            appear.
        second_age: AGE of the second calibration event (e.g. the Ice Age end).
        second_secular_age: Secular age that event's rock should appear.
        chronology: Chronology used to place the Flood.
        k_PF_bracket: Search interval for k_PF.  Widen only if the error says so.
        k_F: In-Flood relaxation constant to hold fixed (default: 0).
        flood_duration: Length of the Flood in true years; defaults to the
            chronology's.  Pass 0.0 when `flood_age` is the Flood's *end*, so
            that the pair sees the post-Flood relaxation alone.

    Returns:
        CalibrationResult with both parameters solved.

    Raises:
        ValueError: If the inputs are out of range, or no k_PF in the bracket
            satisfies both constraints.
    """
    for name, value in (("flood_secular_age", flood_secular_age),
                        ("second_secular_age", second_secular_age)):
        if value <= 0:
            raise ValueError(f"{name} must be positive, got {value!r}")
    if second_age >= flood_age:
        raise ValueError(
            f"second_age ({second_age!r}) must be more recent than flood_age "
            f"({flood_age!r}); these are AGEs, so the more recent event is the "
            "smaller number."
        )

    flood_date = _flood_date_for(flood_age, chronology)
    duration = _resolve_duration(flood_duration, chronology)
    present = chronology.present_date

    def build(lambda_F: float, k_PF: float) -> GeneralModel:
        return GeneralModel.flood_only(
            lambda_F=lambda_F, k_PF=k_PF, t_F=flood_date,
            t_F2=flood_date + duration, k_F=k_F)

    def second_constraint_residual(k_PF: float) -> float:
        """Misfit of the second pair once the Flood pair has pinned lambda_F."""
        lambda_F = solve_lambda_F(flood_age, flood_secular_age, k_PF,
                                  chronology, k_F=k_F,
                                  flood_duration=duration).lambda_F
        return build(lambda_F, k_PF).forward_age(
            second_age, present) - second_secular_age

    lo, hi = k_PF_bracket
    residual_lo = second_constraint_residual(lo)
    residual_hi = second_constraint_residual(hi)
    if residual_lo * residual_hi > 0:
        raise ValueError(
            f"No k_PF in [{lo:g}, {hi:g}] honors both constraints: the second "
            f"pair is missed by {residual_lo:+.4g} yr at k_PF={lo:g} and "
            f"{residual_hi:+.4g} yr at k_PF={hi:g}, without changing sign.  "
            "The two matched date pairs may be mutually inconsistent for this "
            "chronology, or k_PF_bracket may need widening."
        )

    k_PF = brentq(second_constraint_residual, lo, hi, xtol=1e-15, rtol=1e-15)
    lambda_F = solve_lambda_F(flood_age, flood_secular_age, k_PF, chronology,
                              k_F=k_F, flood_duration=duration).lambda_F
    model = build(lambda_F, k_PF)

    return CalibrationResult(
        lambda_F=lambda_F,
        k_PF=k_PF,
        model=model,
        flood_date=flood_date,
        residuals=(
            model.forward_age(flood_age, present) / flood_secular_age - 1.0,
            model.forward_age(second_age, present) / second_secular_age - 1.0,
        ),
        k_F=k_F,
        flood_duration=duration,
    )




def _in_flood_integral(lambda_F2: float, k_F: float, duration: float) -> float:
    """
    Apparent years accumulated across the Flood, given its *end* rate.

    The in-Flood rate is (lambda_F - 1) * exp(-k_F * (t - t_F)) + 1, and
    continuity at t_F2 fixes lambda_F - 1 == (lambda_F2 - 1) * exp(k_F * n).
    Substituting collapses the integral to

        (lambda_F2 - 1) * (exp(k_F * n) - 1) / k_F  +  n

    which is written with expm1 so it stays accurate as k_F -> 0, where it
    tends to lambda_F2 * n — the constant-rate Flood.

    This is monotonically increasing in k_F, from that lower limit to
    arbitrarily large values, which is what makes the solve below a bracketed
    root with no initial guess.
    """
    if k_F <= 0.0:
        return lambda_F2 * duration
    return (lambda_F2 - 1.0) * math.expm1(k_F * duration) / k_F + duration


def solve_flood_rate(
    pre_flood_secular_age: float,
    post_flood_secular_age: float,
    ice_age_secular_age: float,
    chronology: Chronology = DEFAULT_CHRONOLOGY,
    k_PF_bracket: Tuple[float, float] = (1e-6, 1.0),
    k_F_max: float = 100.0,
) -> CalibrationResult:
    """
    Solve lambda_F, k_F and k_PF from three matched pairs.

    The Flood keeps the length the chronology gives it — one year — but lambda
    is no longer constant across it: it starts at ``lambda_F``, relaxes at
    ``k_F``, and hands the post-Flood exponential whatever it has reached by
    ``t_F2``.  That extra degree of freedom is what lets three matched pairs be
    honored by a Flood of a single year:

      1. the pre-Flood contact, at the onset;
      2. the post-Flood contact, at the end;
      3. a later event (the end of the Ice Age), well into the relaxation.

    **The system decouples, so no outer iteration is needed.**  Pairs 2 and 3
    both sit at or after ``t_F2``, where only ``lambda_F2`` and ``k_PF`` enter,
    so `solve_flood_only` pins those two exactly — called with
    ``flood_duration=0.0``, because from the Flood's end onward there is no
    Flood left to integrate.  Pair 1 then differs from pair 2 by the in-Flood
    integral alone, which `_in_flood_integral` reduces to one increasing
    function of ``k_F``.  A single bracketed root gives ``k_F``, and continuity
    gives ``lambda_F``.

    Every residual lands at machine precision, and no step involves an initial
    guess.

    Args:
        pre_flood_secular_age: Secular age rock at the Flood's onset should
            appear (e.g. the Precambrian-Cambrian boundary).
        post_flood_secular_age: Secular age rock at the Flood's end should
            appear (e.g. the K/Pg boundary).
        ice_age_secular_age: Secular age rock at the end of the Ice Age should
            appear.
        chronology: Supplies the Flood's onset and end DATEs and the Ice Age's.
            The Flood's length is an input here, never an unknown.
        k_PF_bracket: Search interval handed to the inner two-pair solve.
        k_F_max: Largest in-Flood relaxation constant to search.  The default
            is far beyond any physically interesting value; a root above it
            means the three pairs demand an implausibly violent Flood.

    Returns:
        CalibrationResult with `k_F` solved and `lambda_F2` available on the
        model, and three residuals in the order (pre-Flood, post-Flood, Ice
        Age).

    Raises:
        ValueError: If the inputs are out of range, if the chronology gives the
            Flood no length, or if the pairs cannot be honored by any k_F in
            [0, k_F_max].
    """
    for name, value in (("pre_flood_secular_age", pre_flood_secular_age),
                        ("post_flood_secular_age", post_flood_secular_age),
                        ("ice_age_secular_age", ice_age_secular_age)):
        if value <= 0:
            raise ValueError(f"{name} must be positive, got {value!r}")
    if post_flood_secular_age >= pre_flood_secular_age:
        raise ValueError(
            f"post_flood_secular_age ({post_flood_secular_age!r}) must be "
            f"younger than pre_flood_secular_age ({pre_flood_secular_age!r}); "
            "the Flood's end is later than its onset, so it must appear "
            "younger."
        )

    duration = chronology.flood_duration
    if duration <= 0.0:
        raise ValueError(
            "this chronology gives the Flood no length "
            f"(flood_start_date == flood_end_date == "
            f"{chronology.flood_start_date!r}), so lambda has no interval to "
            "relax across and the first two pairs collapse onto one another.  "
            "Set flood_end_date > flood_start_date."
        )

    present = chronology.present_date
    flood_end_age = chronology.flood_end_age
    ice_age = chronology.ice_age_end_age

    # Pairs 2 and 3 alone pin the post-Flood relaxation: both sit at or after
    # t_F2, so the Flood behind them contributes nothing to either integral.
    # flood_duration=0.0 says exactly that -- treat t_F2 as the onset.
    tail = solve_flood_only(
        flood_age=flood_end_age,
        flood_secular_age=post_flood_secular_age,
        second_age=ice_age,
        second_secular_age=ice_age_secular_age,
        chronology=chronology,
        k_PF_bracket=k_PF_bracket,
        flood_duration=0.0,
    )
    lambda_F2, k_PF = tail.lambda_F, tail.k_PF

    # Pair 1 differs from pair 2 by the in-Flood integral, which increases
    # monotonically in k_F from lambda_F2 * n upward.
    gap = pre_flood_secular_age - post_flood_secular_age

    def residual(k_F: float) -> float:
        return _in_flood_integral(lambda_F2, k_F, duration) / gap - 1.0

    if residual(0.0) > 0:
        raise ValueError(
            f"the pre-Flood and post-Flood contacts differ by {gap:.6g} "
            f"apparent years, but even a Flood that never relaxes carries "
            f"{lambda_F2 * duration:.6g} across its {duration:g}-year span at "
            f"the rate the later pairs demand (lambda_F2 = {lambda_F2:.6g}).  "
            "The three pairs are mutually inconsistent for this chronology: "
            "the pre-Flood contact would have to be older."
        )
    if residual(k_F_max) < 0:
        raise ValueError(
            f"no k_F in [0, {k_F_max:g}] carries the {gap:.6g} apparent years "
            f"between the pre-Flood and post-Flood contacts across a "
            f"{duration:g}-year Flood.  Raise k_F_max if such a Flood is "
            "intended, or check the two contacts."
        )

    k_F = brentq(residual, 0.0, k_F_max, xtol=1e-15, rtol=1e-15)
    lambda_F = (lambda_F2 - 1.0) * math.exp(k_F * duration) + 1.0

    model = GeneralModel(GeneralModelParams(
        lambda_c=1.0, lambda_F=lambda_F, lambda_bg=1.0,
        k_c=0.0, k_F=k_F, k_PF=k_PF, t_c=1.0,
        t_F=chronology.flood_start_date,
        t_F2=chronology.flood_end_date,
    ))

    return CalibrationResult(
        lambda_F=lambda_F,
        k_PF=k_PF,
        model=model,
        flood_date=chronology.flood_start_date,
        residuals=(
            model.forward_age(chronology.flood_start_age, present)
            / pre_flood_secular_age - 1.0,
            model.forward_age(flood_end_age, present)
            / post_flood_secular_age - 1.0,
            model.forward_age(ice_age, present) / ice_age_secular_age - 1.0,
        ),
        k_F=k_F,
        flood_duration=duration,
    )
