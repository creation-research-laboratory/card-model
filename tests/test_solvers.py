"""
Tests for `card._solvers.brentq`, the stdlib replacement for scipy's.

The headline test is `test_matches_scipy_bit_for_bit`.  `_solvers.brentq` is a
port of the algorithm in scipy's ``Zeros/brentq.c``, and the reason the package
can drop its scipy dependency without re-pinning a single characterization
number is that the port returns the *same float*, not merely a close one.  That
is a checkable claim, so it is checked — against scipy itself, which the dev
environment has even though the package no longer needs it at runtime.
"""

import math

import pytest

from card._solvers import brentq
from card.calibrate import solve_flood_only
from card.constants import AGE_OF_EARTH, FLOOD_AGE, ICE_AGE_END_AGE
from card.models import GeneralModel

scipy_optimize = pytest.importorskip(
    "scipy.optimize",
    reason="scipy is a dev-time dependency here; the package no longer needs it",
)


# ----------------------------------------------------------------------------
# Parity with scipy
# ----------------------------------------------------------------------------

# Functions chosen to exercise the branches that differ between implementations:
# a straight line (secant step), a cubic with curvature (inverse quadratic
# interpolation), something very flat near the root (the bisection fallback
# guard), and something steep (tests the delta-sized minimum step).
PARITY_CASES = [
    ("linear", lambda x: 2.0 * x - 3.0, -10.0, 10.0),
    ("cubic", lambda x: x ** 3 - 2.0 * x - 5.0, 1.0, 4.0),
    ("flat_near_root", lambda x: (x - 1.5) ** 5, 0.0, 4.0),
    ("steep", lambda x: math.exp(x) - 1e6, -5.0, 30.0),
    ("log_scaled", lambda x: 10.0 ** x - 12345.0, 0.0, 12.0),
    ("near_zero_root", lambda x: x - 1e-12, -1.0, 1.0),
    ("root_at_bracket_interior", lambda x: math.sin(x), 3.0, 4.0),
]


@pytest.mark.parametrize("label,f,a,b", PARITY_CASES,
                         ids=[c[0] for c in PARITY_CASES])
def test_matches_scipy_bit_for_bit(label, f, a, b):
    ours = brentq(f, a, b)
    theirs = scipy_optimize.brentq(f, a, b)
    assert ours == theirs, f"{label}: {ours!r} != {theirs!r}"


@pytest.mark.parametrize("xtol,rtol", [
    (2e-12, 8.881784197001252e-16),   # the defaults
    (1e-10, 1e-15),                   # what models.inverse_age uses
    (1e-12, 8.881784197001252e-16),   # what calibrate.solve_lambda_F uses
    (1e-15, 1e-15),                   # what calibrate.solve_flood_only uses
])
def test_matches_scipy_at_the_tolerances_the_package_uses(xtol, rtol):
    f = lambda x: x ** 3 - 2.0 * x - 5.0
    assert (brentq(f, 1.0, 4.0, xtol=xtol, rtol=rtol)
            == scipy_optimize.brentq(f, 1.0, 4.0, xtol=xtol, rtol=rtol))


def test_matches_scipy_on_a_real_inverse_age_solve():
    """The actual objective `inverse_age` hands the solver, across the range."""
    model = GeneralModel.flood_only(lambda_F=3.22367e6, k_F=0.00596981)
    for target in (1.0, 1e3, 11500.0, 1e6, 66e6, 540e6,
                   model.max_secular_age() * 0.999):
        objective = lambda age: model.forward_age(age, AGE_OF_EARTH) - target
        ours = brentq(objective, 0.0, AGE_OF_EARTH, xtol=1e-10, rtol=1e-15,
                      maxiter=200)
        theirs = scipy_optimize.brentq(objective, 0.0, AGE_OF_EARTH,
                                       xtol=1e-10, rtol=1e-15, maxiter=200)
        assert ours == theirs, f"target {target:g}: {ours!r} != {theirs!r}"


# ----------------------------------------------------------------------------
# Correctness in its own right
# ----------------------------------------------------------------------------

def test_finds_a_known_root():
    assert brentq(lambda x: x ** 2 - 4.0, 0.0, 10.0) == pytest.approx(2.0)


def test_returns_an_exact_endpoint_root_without_iterating():
    """A zero at either end is the answer; the sign test must not reject it."""
    assert brentq(lambda x: x, 0.0, 1.0) == 0.0
    assert brentq(lambda x: x - 1.0, 0.0, 1.0) == 1.0


def test_unbracketed_interval_raises():
    with pytest.raises(ValueError, match="must have different signs"):
        brentq(lambda x: x ** 2 + 1.0, -1.0, 1.0)


def test_same_sign_endpoints_raise_even_when_a_root_exists_between():
    """Brent's method needs a sign change; a double root is not one, and
    silently returning something plausible is exactly what this package's
    error contract forbids."""
    with pytest.raises(ValueError, match="must have different signs"):
        brentq(lambda x: x ** 2, -1.0, 1.0)


def test_exhausting_maxiter_raises_rather_than_returning_a_guess():
    with pytest.raises(RuntimeError, match="failed to converge"):
        brentq(lambda x: x ** 3 - 2.0 * x - 5.0, 1.0, 4.0, maxiter=2)


@pytest.mark.parametrize("xtol", [0.0, -1e-12])
def test_non_positive_xtol_raises(xtol):
    with pytest.raises(ValueError, match="xtol must be positive"):
        brentq(lambda x: x, -1.0, 1.0, xtol=xtol)


def test_rtol_below_machine_precision_raises():
    """scipy rejects this rather than looping to maxiter; so do we."""
    with pytest.raises(ValueError, match="rtol must be at least"):
        brentq(lambda x: x, -1.0, 1.0, rtol=1e-20)


def test_args_are_forwarded():
    assert brentq(lambda x, offset: x - offset, -10.0, 10.0,
                  args=(3.0,)) == pytest.approx(3.0)


def test_the_calibration_solve_still_lands_on_its_recorded_values():
    """
    Guards the swap at the level that matters: the package's headline solve.

    `tests/test_calibrate.py` pins these too, but this asserts them against the
    solver directly, so a regression here reads as a solver bug rather than a
    model one.
    """
    result = solve_flood_only(FLOOD_AGE, 540.0e6, ICE_AGE_END_AGE, 11500.0)
    assert result.lambda_F == pytest.approx(3.22367e6, rel=1e-5)
    assert result.k_F == pytest.approx(0.00596981, rel=1e-5)
    assert result.max_abs_residual < 1e-12
