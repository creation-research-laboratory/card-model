"""
Deterministic calibration of the flood-only model from matched date pairs.

A "matched date pair" is one event dated two ways: a young AGE (years before
present) and the secular age the rock would appear to have.  Each pair is one
equation, so:

  * one pair determines one parameter — `solve_lambda_F` fixes k_F and solves
    for lambda_F;
  * two pairs determine both — `solve_flood_only` solves the 2x2 system so both
    dates are honored exactly.

This is the deterministic counterpart to `card.inference`.  Use it when the
constraints are exact and you want the answer; use MCMC when the constraints
have uncertainties and you want a posterior.

Extracted from examples/plot_model_calibration.py and its _joint variant, which
each carried their own copy of the solve.

Like `models.py`, this module is standard-library only — the root solve comes
from `card._solvers` rather than scipy — so calibration runs anywhere CPython
does, including a browser under Pyodide.
"""

from dataclasses import dataclass
from typing import Tuple

from ._solvers import brentq
from .chronology import DEFAULT_CHRONOLOGY, Chronology
from .models import GeneralModel

__all__ = [
    "CalibrationResult",
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
        lambda_F: Solved Flood decay rate, as a multiple of background.
        k_F: Post-Flood relaxation constant (solved, or the value supplied).
        model: The calibrated model, ready to use.
        flood_date: DATE of the Flood the model was built with.
        residuals: Relative misfit of each constraint, as
            ``predicted / target - 1``.  All entries should be ~1e-12.
    """

    lambda_F: float
    k_F: float
    model: GeneralModel
    flood_date: float
    residuals: Tuple[float, ...]

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


def solve_lambda_F(
    flood_age: float,
    flood_secular_age: float,
    k_F: float,
    chronology: Chronology = DEFAULT_CHRONOLOGY,
) -> CalibrationResult:
    """
    Solve for lambda_F so one matched date pair is honored, with k_F given.

    The secular age is strictly increasing in lambda_F at fixed k_F, so the
    root is unique and bisection finds it without an initial guess.

    Args:
        flood_age: AGE (years before present) at which the Flood occurred.
        flood_secular_age: Secular age that Flood-formed rock should appear.
        k_F: Post-Flood relaxation constant to hold fixed.
        chronology: Chronology used to place the Flood (default: the package's).

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

    def residual(log10_lambda_F: float) -> float:
        model = GeneralModel.flood_only(lambda_F=10.0 ** log10_lambda_F,
                                        k_F=k_F, t_F=flood_date)
        return model.forward_age(flood_age,
                                 chronology.present_date) - flood_secular_age

    lo, hi = _LOG10_LAMBDA_BRACKET
    if residual(lo) > 0 or residual(hi) < 0:
        raise ValueError(
            f"No lambda_F in [10^{lo:g}, 10^{hi:g}] reproduces a secular age of "
            f"{flood_secular_age:.4g} for a Flood at {flood_age:g} YBP with "
            f"k_F = {k_F:g}.  Check the constraint, or widen the bracket."
        )

    lambda_F = 10.0 ** brentq(residual, lo, hi, xtol=1e-12)
    model = GeneralModel.flood_only(lambda_F=lambda_F, k_F=k_F, t_F=flood_date)
    predicted = model.forward_age(flood_age, chronology.present_date)
    return CalibrationResult(
        lambda_F=lambda_F,
        k_F=k_F,
        model=model,
        flood_date=flood_date,
        residuals=(predicted / flood_secular_age - 1.0,),
    )


def solve_flood_only(
    flood_age: float,
    flood_secular_age: float,
    second_age: float,
    second_secular_age: float,
    chronology: Chronology = DEFAULT_CHRONOLOGY,
    k_F_bracket: Tuple[float, float] = (1e-6, 1.0),
) -> CalibrationResult:
    """
    Solve for both lambda_F and k_F so two matched date pairs are honored.

    Two constraints, two unknowns: the solve is exact rather than a fit, and
    both residuals come back at machine precision.

    Implemented as two *nested bracketed* solves rather than a 2-D
    Newton-style solve.  For any candidate k_F the Flood constraint pins
    lambda_F by a monotone 1-D root (`solve_lambda_F`), which reduces the
    system to a single equation in k_F alone.  That residual runs from
    positive at small k_F (the rate barely relaxes, so the second event looks
    far too old) to negative at large k_F (the rate is back to background
    before the second event), so a sign change is guaranteed and bisection
    always converges.

    The alternative — handing both unknowns to `fsolve` with an initial guess —
    is what the original scripts did, and it silently wandered to
    lambda_F ~ 1e-8 on chronologies whose guess was slightly off.  Bracketing
    removes the guess and the failure mode together.

    Args:
        flood_age: AGE at which the Flood occurred.
        flood_secular_age: Secular age Flood-formed rock should appear.
        second_age: AGE of the second calibration event (e.g. the Ice Age end).
        second_secular_age: Secular age that event's rock should appear.
        chronology: Chronology used to place the Flood.
        k_F_bracket: Search interval for k_F.  Widen only if the error says so.

    Returns:
        CalibrationResult with both parameters solved.

    Raises:
        ValueError: If the inputs are out of range, or no k_F in the bracket
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
    present = chronology.present_date

    def second_constraint_residual(k_F: float) -> float:
        """Misfit of the second pair once the Flood pair has pinned lambda_F."""
        lambda_F = solve_lambda_F(flood_age, flood_secular_age, k_F,
                                  chronology).lambda_F
        model = GeneralModel.flood_only(lambda_F=lambda_F, k_F=k_F,
                                        t_F=flood_date)
        return model.forward_age(second_age, present) - second_secular_age

    lo, hi = k_F_bracket
    residual_lo = second_constraint_residual(lo)
    residual_hi = second_constraint_residual(hi)
    if residual_lo * residual_hi > 0:
        raise ValueError(
            f"No k_F in [{lo:g}, {hi:g}] honors both constraints: the second "
            f"pair is missed by {residual_lo:+.4g} yr at k_F={lo:g} and "
            f"{residual_hi:+.4g} yr at k_F={hi:g}, without changing sign.  "
            "The two matched date pairs may be mutually inconsistent for this "
            "chronology, or k_F_bracket may need widening."
        )

    k_F = brentq(second_constraint_residual, lo, hi, xtol=1e-15, rtol=1e-15)
    lambda_F = solve_lambda_F(flood_age, flood_secular_age, k_F,
                              chronology).lambda_F
    model = GeneralModel.flood_only(lambda_F=lambda_F, k_F=k_F, t_F=flood_date)

    return CalibrationResult(
        lambda_F=lambda_F,
        k_F=k_F,
        model=model,
        flood_date=flood_date,
        residuals=(
            model.forward_age(flood_age, present) / flood_secular_age - 1.0,
            model.forward_age(second_age, present) / second_secular_age - 1.0,
        ),
    )
