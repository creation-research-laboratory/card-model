"""
Tests for GeneralModelParams validation.

Before this validation existed, every one of the invalid parameter sets below
was accepted silently and returned a plausible-looking number — including a
negative secular age, an infinite one, and a Flood that ended before it began
(which made the third region of lambda_func unreachable, silently changing the
shape of the model rather than erroring).
"""

import numpy as np
import pytest

from card import (
    FLOOD_END_DATE,
    FLOOD_START_DATE,
    LAMBDA_BG,
    MAX_UNREMARKED_FLOOD_DURATION,
    GeneralModel,
    GeneralModelParams,
)


def make_params(**overrides):
    """Valid baseline parameters, with overrides applied."""
    kwargs = dict(
        lambda_c=1e3,
        lambda_F=1e5,
        lambda_bg=1.0,
        k_c=1e-1,
        k_F=8.04e-3,
        t_c=1,
        t_F=1656,
        t_F2=1657,
    )
    kwargs.update(overrides)
    return GeneralModelParams(**kwargs)


def test_baseline_parameters_are_valid():
    assert make_params().lambda_bg == 1.0


# ----------------------------------------------------------------------------
# Decay rates: normalized to background, so every lambda must be >= 1
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["lambda_c", "lambda_F"])
@pytest.mark.parametrize("value", [0.0, 0.5, -1e5])
def test_decay_rates_below_background_are_rejected(field, value):
    with pytest.raises(ValueError, match="must be >= 1"):
        make_params(**{field: value})


@pytest.mark.parametrize("field", ["lambda_c", "lambda_F"])
def test_decay_rate_exactly_at_background_is_allowed(field):
    """lambda == lambda_bg is the no-acceleration limit the flood-only model
    relies on, so it must remain legal."""
    assert getattr(make_params(**{field: 1.0}), field) == 1.0


def test_zero_background_rate_is_rejected():
    with pytest.raises(ValueError, match="lambda_bg must be positive"):
        make_params(lambda_bg=0.0)


def test_nonunit_background_rate_is_normalized_to_one():
    with pytest.warns(UserWarning, match="lambda_bg was"):
        params = make_params(lambda_c=2e3, lambda_F=2e5, lambda_bg=2.0)
    assert params.lambda_bg == 1.0
    assert params.lambda_c == pytest.approx(1e3)
    assert params.lambda_F == pytest.approx(1e5)


def test_normalization_preserves_results():
    """Only ratios to background are meaningful, so scaling every rate by the
    same factor must not change any computed age."""
    baseline = GeneralModel(make_params())
    with pytest.warns(UserWarning):
        scaled = GeneralModel(make_params(lambda_c=3e3, lambda_F=3e5,
                                          lambda_bg=3.0))
    for age in [100, 1000, 4400, 5000]:
        assert scaled.forward_age(age) == pytest.approx(
            baseline.forward_age(age), rel=1e-12)


# ----------------------------------------------------------------------------
# Relaxation constants: k >= 0 is what makes lambda decay toward background
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["k_c", "k_F"])
def test_negative_relaxation_constants_are_rejected(field):
    with pytest.raises(ValueError, match="must be >= 0"):
        make_params(**{field: -8e-3})


@pytest.mark.parametrize("field", ["k_c", "k_F"])
def test_zero_relaxation_constant_is_allowed(field):
    """k == 0 means lambda never relaxes.  run_card_mcmc.py pins k_c = 0."""
    assert getattr(make_params(**{field: 0.0}), field) == 0.0


def test_positive_k_actually_decays():
    """Guards the sign convention: with the minus sign already in the
    exponent, a positive k must make lambda fall back toward background."""
    model = GeneralModel(make_params())
    rates = [model.lambda_func(t) for t in [1658, 1700, 2000, 3000, 6056]]
    assert rates == sorted(rates, reverse=True)
    assert rates[-1] == pytest.approx(LAMBDA_BG, rel=1e-6)


# ----------------------------------------------------------------------------
# Event dates must be ordered t_c <= t_F <= t_F2
# ----------------------------------------------------------------------------

def test_flood_ending_before_it_starts_is_rejected():
    with pytest.raises(ValueError, match="cannot end before it starts"):
        make_params(t_F=1656, t_F2=1000)


def test_creation_week_ending_after_the_flood_is_rejected():
    with pytest.raises(ValueError, match="must be ordered"):
        make_params(t_c=3000, t_F=1656)


def test_negative_creation_date_is_rejected():
    with pytest.raises(ValueError, match="must be >= 0"):
        make_params(t_c=-1)


def test_instantaneous_flood_is_allowed():
    """t_F == t_F2 is the limit GeneralModel.flood_only() constructs."""
    params = make_params(t_F=FLOOD_START_DATE, t_F2=FLOOD_END_DATE)
    assert params.t_F == params.t_F2


def test_long_flood_warns_but_is_permitted():
    duration = MAX_UNREMARKED_FLOOD_DURATION + 1.0
    with pytest.warns(UserWarning, match="Flood duration"):
        params = make_params(t_F=1656, t_F2=1656 + duration)
    assert params.t_F2 - params.t_F == pytest.approx(duration)


def test_flood_at_the_warning_threshold_is_silent(recwarn):
    make_params(t_F=1656, t_F2=1656 + MAX_UNREMARKED_FLOOD_DURATION)
    assert [w for w in recwarn if "Flood duration" in str(w.message)] == []


def test_flood_dates_given_as_ages_trip_the_warning():
    """A common slip: passing AGEs (years before present) where DATEs belong.
    Flood 4400 -> 4400 YBP reads as a 0-length Flood, but an Ice-Age-style
    pair like (2556, 4400) is a 1844-year Flood, which gets flagged."""
    with pytest.warns(UserWarning, match="not ages before present"):
        make_params(t_c=1, t_F=2556, t_F2=4400)


# ----------------------------------------------------------------------------
# Non-finite input
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["lambda_c", "lambda_F", "lambda_bg",
                                   "k_c", "k_F", "t_c", "t_F", "t_F2"])
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_non_finite_parameters_are_rejected(field, value):
    with pytest.raises(ValueError, match="must be finite"):
        make_params(**{field: value})


# ----------------------------------------------------------------------------
# The exact cases that used to be accepted silently
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("label, overrides", [
    ("flood ends before it starts", dict(lambda_c=1.0, t_F=1656, t_F2=1000)),
    ("creation week ends after flood", dict(t_c=3000, t_F=1656)),
    ("negative k_F", dict(lambda_c=1.0, k_F=-8e-3)),
    ("zero background rate", dict(lambda_c=1.0, lambda_bg=0.0)),
    ("negative lambda_F", dict(lambda_c=1.0, lambda_F=-1e5)),
])
def test_previously_silent_bad_parameters_now_raise(label, overrides):
    with pytest.raises(ValueError):
        make_params(**overrides)
