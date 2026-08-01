"""
Unit tests for the decay models in decay_solver.py.

Ported from the print-style test functions that used to live at the bottom
of decay_solver.py (test_age_zero_boundary, test_round_trip_forward_inverse,
test_inverse_forward_consistency), converted to asserting pytest tests.

The flood-only model is now exercised through the GeneralModel.flood_only()
factory (the old standalone FloodOnlyModel class, whose post-Flood exponential
was anchored at the present rather than at the Flood, has been removed).
"""

import numpy as np
import pytest

from card import (
    ACCEPTABLE_ERROR,
    AGE_OF_EARTH,
    ConstantDecayModel,
    GeneralModel,
    GeneralModelParams,
    years_after_creation_to_years_before_present,
    years_before_present_to_years_after_creation,
)


# Standard GeneralModel parameters used by the original test suite.
STANDARD_GENERAL_PARAMS = GeneralModelParams(
    lambda_c=1e3,
    lambda_F=1e5,
    lambda_bg=1.0,
    k_c=1e-1,
    k_F=8.04e-3,
    t_c=1,
    t_F=1656,
    t_F2=1657,
)

# True ages (YBP) chosen to exercise distinct model regions:
#   0    : rock formed at the present (boundary)
#   100  : post-Flood, decay fully at background -> secular ~= true
#   4000 : post-Flood but within the accelerated-decay tail
#   4200 : late pre-Flood/post-Flood transition region
#   5000 : pre-Flood, spans the Flood event -> large secular age
# Ages deeper than ~4400 YBP map onto a near-plateau of secular age (the
# post-Flood decay integral dominates), which makes the inverse problem
# ill-conditioned there — those ages are excluded from round-trip tests.
ROUND_TRIP_TRUE_AGES = [0, 100, 4000, 4200, 5000]

# Secular ages for the inverse -> forward round trip, given as fractions of
# each model's own maximum achievable secular age.  Absolute values cannot be
# shared across models: the constant model tops out at AGE_OF_EARTH while the
# accelerated ones reach into the millions of years, and asking any model for a
# secular age it cannot produce is a domain error, not a round trip.
ROUND_TRIP_SECULAR_FRACTIONS = [0.0, 1e-6, 1e-3, 0.1, 0.5, 1.0]


def make_constant():
    return ConstantDecayModel(lambda_bg=1.0)


def make_flood_only():
    return GeneralModel.flood_only(lambda_F=1e5, k_F=8.04e-3)


def make_general():
    return GeneralModel(STANDARD_GENERAL_PARAMS)


MODEL_FACTORIES = {
    "constant": make_constant,
    "flood_only": make_flood_only,
    "general": make_general,
}


@pytest.fixture(params=MODEL_FACTORIES.keys())
def model(request):
    return MODEL_FACTORIES[request.param]()


# ----------------------------------------------------------------------------
# Boundary condition: age 0 (rock formed at the present)
# ----------------------------------------------------------------------------

def test_age_zero_boundary(model):
    assert model.forward_age(0) == pytest.approx(0.0, abs=1e-12)
    assert model.inverse_age(0) == pytest.approx(0.0, abs=1e-12)


# ----------------------------------------------------------------------------
# Round trip: forward -> inverse recovers the true age
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("true_age", ROUND_TRIP_TRUE_AGES)
def test_forward_then_inverse_recovers_true_age(model, true_age):
    secular = model.forward_age(true_age)
    recovered = model.inverse_age(secular)
    assert recovered == pytest.approx(true_age, rel=ACCEPTABLE_ERROR, abs=1e-6)


# ----------------------------------------------------------------------------
# Round trip: inverse -> forward recovers the secular age
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("fraction", ROUND_TRIP_SECULAR_FRACTIONS)
def test_inverse_then_forward_recovers_secular_age(model, fraction):
    secular_age = fraction * model.max_secular_age()
    true_age = model.inverse_age(secular_age)
    recovered = model.forward_age(true_age)
    assert recovered == pytest.approx(secular_age, rel=ACCEPTABLE_ERROR, abs=1e-6)


def test_max_secular_age_is_the_top_of_the_domain(model):
    """The ceiling is the secular age of a rock formed on Day 1 of Creation,
    and asking for anything above it is a domain error."""
    ceiling = model.max_secular_age()
    assert model.forward_age(AGE_OF_EARTH) == pytest.approx(ceiling, rel=1e-12)
    assert model.inverse_age(ceiling) == pytest.approx(AGE_OF_EARTH, rel=1e-9)
    with pytest.raises(ValueError, match="exceeds the maximum"):
        model.inverse_age(ceiling * 1.0001 + 1.0)


# ----------------------------------------------------------------------------
# Unified error contract
#
# Every model rejects invalid input the same way: ValueError, never a NaN
# sentinel and never a plausible-looking number.  forward_age used to return
# NaN for negative ages (to keep the old fsolve inverse from raising), which
# meant a caller who did not check could propagate NaN silently.
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("bad_age", [-1.0, -1e-12, np.nan, np.inf, -np.inf])
def test_forward_age_rejects_invalid_ages(model, bad_age):
    with pytest.raises(ValueError):
        model.forward_age(bad_age)


@pytest.mark.parametrize("bad_age", [-1.0, np.nan, np.inf, -np.inf])
def test_inverse_age_rejects_invalid_ages(model, bad_age):
    with pytest.raises(ValueError):
        model.inverse_age(bad_age)


def test_forward_age_never_returns_nan(model):
    """No NaN sentinels anywhere in the valid domain."""
    for true_age in np.linspace(0, AGE_OF_EARTH, 200):
        assert np.isfinite(model.forward_age(true_age))


@pytest.mark.parametrize("bad_present", [0, -1, np.nan, np.inf])
def test_invalid_present_time_is_rejected(model, bad_present):
    with pytest.raises(ValueError, match="present_time"):
        model.forward_age(100, present_time=bad_present)


@pytest.mark.parametrize("bad_type", ["4400", None, [4400], True])
def test_non_numeric_ages_are_rejected(model, bad_type):
    with pytest.raises(ValueError, match="real number"):
        model.forward_age(bad_type)


def test_every_model_rejects_formation_before_creation(model):
    """Uniform across models: an age beyond present_time places formation
    before Day 1 of Creation."""
    with pytest.raises(ValueError, match="exceeds present_time"):
        model.forward_age(AGE_OF_EARTH + 1)


# ----------------------------------------------------------------------------
# Domain validation for the GeneralModel
# ----------------------------------------------------------------------------

def test_forward_age_rejects_formation_before_creation():
    general = make_general()
    with pytest.raises(ValueError):
        general.forward_age(65e6)  # true age far beyond AGE_OF_EARTH


def test_inverse_age_rejects_unachievable_secular_age():
    general = make_general()
    max_secular = general.forward_age(AGE_OF_EARTH)
    with pytest.raises(ValueError):
        general.inverse_age(max_secular * 10)


def test_negative_ages_rejected(model):
    with pytest.raises(ValueError):
        model.inverse_age(-1.0)


# ----------------------------------------------------------------------------
# flood_only factory produces the intended GeneralModel limit
# ----------------------------------------------------------------------------

def test_flood_only_factory_matches_explicit_params():
    factory_model = GeneralModel.flood_only(lambda_F=1e5, k_F=8.04e-3, t_F=1656)
    explicit_model = GeneralModel(GeneralModelParams(
        lambda_c=1.0,
        lambda_F=1e5,
        lambda_bg=1.0,
        k_c=1.0,
        k_F=8.04e-3,
        t_c=1.0,
        t_F=1656,
        t_F2=1656,
    ))
    for true_age in [100, 1000, 4000, 5000]:
        assert factory_model.forward_age(true_age) == pytest.approx(
            explicit_model.forward_age(true_age), rel=1e-12)


def test_flood_only_rate_is_background_before_flood():
    m = GeneralModel.flood_only(lambda_F=1e5, k_F=8.04e-3, t_F=1656)
    assert m.lambda_func(1000) == pytest.approx(1.0)
    assert m.lambda_func(1657) < 1e5
    assert m.lambda_func(1657) > 1.0


# ----------------------------------------------------------------------------
# Structural properties of forward_age / inverse_age
#
# These pin properties the model must satisfy for any parameters, rather than
# specific numbers.  They are what caught the quadrature bug: forward_age
# integrates a non-negative lambda, so it cannot decrease, yet the old
# quad-without-breakpoints implementation produced backward steps of up to
# 1e5-1e9 years near the Flood discontinuity.
# ----------------------------------------------------------------------------

# A short, intense Flood — the regime where the old fsolve-based inverse
# failed on ~17% of targets.
SHORT_FLOOD_PARAMS = GeneralModelParams(
    lambda_c=1.0,
    lambda_F=5e8,
    lambda_bg=1.0,
    k_c=1.0,
    k_F=5e-3,
    t_c=1.0,
    t_F=1656.0,
    t_F2=1656.5,
)


def test_forward_age_is_monotone(model):
    true_ages = np.linspace(0, AGE_OF_EARTH, 2000)
    secular = np.array([model.forward_age(t) for t in true_ages])
    steps = np.diff(secular)
    # Allow only floating-point-scale dips, not quadrature-scale ones.
    tolerance = 1e-12 * np.max(np.abs(secular))
    assert steps.min() >= -tolerance


def test_forward_age_is_monotone_for_short_intense_flood():
    model = GeneralModel(SHORT_FLOOD_PARAMS)
    true_ages = np.linspace(0, AGE_OF_EARTH, 2000)
    secular = np.array([model.forward_age(t) for t in true_ages])
    steps = np.diff(secular)
    tolerance = 1e-12 * np.max(np.abs(secular))
    assert steps.min() >= -tolerance


@pytest.mark.parametrize("params", [STANDARD_GENERAL_PARAMS, SHORT_FLOOD_PARAMS])
def test_inverse_age_round_trips_across_full_secular_range(params):
    """Dense sweep of the achievable secular range; every target must invert."""
    model = GeneralModel(params)
    max_secular = model.forward_age(AGE_OF_EARTH)
    for fraction in np.logspace(-9, 0, 200):
        target = max_secular * fraction
        true_age = model.inverse_age(target)
        assert 0.0 <= true_age <= AGE_OF_EARTH
        assert model.forward_age(true_age) == pytest.approx(target, rel=1e-9)


@pytest.mark.parametrize("k_F", [1e-3, 1e-8, 1e-12, 0.0])
def test_integral_is_stable_as_decay_constant_approaches_zero(k_F):
    """k -> 0 means lambda never relaxes; the integral must stay finite and
    approach the constant-rate limit rather than dividing by zero."""
    lambda_F = 1e5
    t_F = 1656
    model = GeneralModel.flood_only(lambda_F=lambda_F, k_F=k_F, t_F=t_F)
    secular = model.forward_age(AGE_OF_EARTH)
    assert np.isfinite(secular)

    post_flood_span = AGE_OF_EARTH - t_F
    if k_F * post_flood_span < 1e-4:
        # lambda barely relaxes, so the result approaches the constant-rate
        # limit.  The leading correction is k*span/2 in relative terms, so the
        # tolerance has to admit it; at k_F == 0 the match is exact.
        expected = t_F + lambda_F * post_flood_span
        tolerance = max(1e-15, k_F * post_flood_span)
        assert secular == pytest.approx(expected, rel=tolerance)


# ----------------------------------------------------------------------------
# Time convention conversion helpers
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("ybp", [0, 1656, 4400, AGE_OF_EARTH])
def test_time_convention_round_trip(ybp):
    after_creation = years_before_present_to_years_after_creation(ybp)
    assert years_after_creation_to_years_before_present(after_creation) == ybp
    assert after_creation == AGE_OF_EARTH - ybp
