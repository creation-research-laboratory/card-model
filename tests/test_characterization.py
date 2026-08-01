"""
Characterization tests: pin currently known-good numbers.

These tests freeze the numerical behavior of the code as of 2026-07-19 so the
planned restructuring (splitting decay_solver.py into a package, generalizing
the MCMC fitter, etc.) can be verified not to change any results.  The pinned
values were computed with the pre-refactor code and cross-checked against
todo.md's recorded calibration solutions.

If a deliberate model change alters these numbers, update the pins in the
same commit and say why in the commit message.

Note: the Ice Age constant's convention ambiguity was resolved 2026-07-19 and
the names were made self-describing on 2026-07-26 — ICE_AGE_END_DATE is years
after Creation (3500) and ICE_AGE_END_AGE is years before present (2556).
These tests pin behavior for explicit numeric inputs only, so they were
unaffected by both changes.
"""

import numpy as np
import pytest

from card.decay_solver import (
    AGE_OF_EARTH,
    GeneralModel,
    GeneralModelParams,
)


# ----------------------------------------------------------------------------
# Standard test-suite GeneralModel (Creation pulse + Flood)
# ----------------------------------------------------------------------------

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

# (true_age_YBP, expected_secular_age)
STANDARD_FORWARD_PINS = [
    (100, 100.00000000670049),
    (4000, 506967.91547301115),
    (4200, 2515426.0568526606),
    (5000, 12542685.567458514),
    (AGE_OF_EARTH, 12554730.572396468),  # maximum achievable secular age
]


@pytest.mark.parametrize("true_age, expected_secular", STANDARD_FORWARD_PINS)
def test_standard_general_model_forward_ages(true_age, expected_secular):
    model = GeneralModel(STANDARD_GENERAL_PARAMS)
    assert model.forward_age(true_age) == pytest.approx(expected_secular, rel=1e-6)


# ----------------------------------------------------------------------------
# MCMC posterior-median flood-only model (values from the fitted inversion,
# also used by the __main__ demo block of decay_solver.py)
# ----------------------------------------------------------------------------

POSTERIOR_LAMBDA_F = 10 ** 5.7628
POSTERIOR_K_F = 10 ** -2.8562


def make_posterior_model():
    return GeneralModel.flood_only(lambda_F=POSTERIOR_LAMBDA_F,
                                   k_F=POSTERIOR_K_F,
                                   t_F=1656)


def test_posterior_model_flood_rock_secular_age():
    # A rock formed at the Flood (4400 YBP) appears ~415 Myr old.
    model = make_posterior_model()
    assert model.forward_age(4400) == pytest.approx(415006372.3893613, rel=1e-6)


def test_posterior_model_max_secular_age():
    # Re-pinned when compute_integral moved from scipy quad to the exact
    # closed form.  The previous pin (415044227.5221515) was quadrature error:
    # quad, given no breakpoints, misplaced ~8.7e-5 of an integral spanning the
    # Flood discontinuity.  The value below is the analytically exact one and
    # agrees with analytic_flood_only_secular_age() to ~1e-16.
    model = make_posterior_model()
    assert model.forward_age(AGE_OF_EARTH) == pytest.approx(415008028.38936144, rel=1e-12)


def test_posterior_model_inverse_of_65_myr():
    # A rock that appears 65 Myr old truly formed ~3077 years ago.
    model = make_posterior_model()
    assert model.inverse_age(65e6) == pytest.approx(3077.029544861473, rel=1e-6)


def test_posterior_model_cannot_produce_540_myr():
    # This model's ceiling (~4.15e8 yr) is below 540 Myr; inverting 540 Myr
    # must raise rather than return a spurious age.
    model = make_posterior_model()
    with pytest.raises(ValueError):
        model.inverse_age(540e6)


# ----------------------------------------------------------------------------
# Calibration solutions (recorded in todo.md, 2026-07-11)
#
# Joint solve: (lambda_F, k_F) chosen so BOTH paired dates are honored:
#     forward_age(flood_ybp)   = 541 Ma   (Precambrian-Cambrian boundary)
#     forward_age(ice_age_ybp) = 12 ka    (end of the Ice Age)
# ----------------------------------------------------------------------------

FLOOD_SECULAR = 541e6
ICE_AGE_SECULAR = 12e3

# (flood_ybp, ice_age_ybp, solved_lambda_F, solved_k_F)
JOINT_CALIBRATION_PINS = [
    (5324, 4200, 5365205.470625984, 0.009917296248264706),
    (4374, 3500, 6846690.80098783, 0.012655721177656678),
]


@pytest.mark.parametrize("flood_ybp, ice_ybp, lambda_F, k_F",
                         JOINT_CALIBRATION_PINS)
def test_joint_calibration_solutions_honor_both_dates(flood_ybp, ice_ybp,
                                                      lambda_F, k_F):
    model = GeneralModel.flood_only(lambda_F=lambda_F, k_F=k_F,
                                    t_F=AGE_OF_EARTH - flood_ybp)
    assert model.forward_age(flood_ybp) == pytest.approx(FLOOD_SECULAR, rel=1e-6)
    assert model.forward_age(ice_ybp) == pytest.approx(ICE_AGE_SECULAR, rel=1e-6)


# Fixed-k_F solve: k_F specified, lambda_F solved so the Flood pair is exact.
# (flood_ybp, k_F, solved_lambda_F)
FIXED_KF_CALIBRATION_PINS = [
    (5324, 0.0097, 5247649.357200022),
    (4374, 0.0124, 6708346.762400001),
]


@pytest.mark.parametrize("flood_ybp, k_F, lambda_F", FIXED_KF_CALIBRATION_PINS)
def test_fixed_kf_calibration_solutions_honor_flood_date(flood_ybp, k_F,
                                                         lambda_F):
    model = GeneralModel.flood_only(lambda_F=lambda_F, k_F=k_F,
                                    t_F=AGE_OF_EARTH - flood_ybp)
    assert model.forward_age(flood_ybp) == pytest.approx(FLOOD_SECULAR, rel=1e-6)


# ----------------------------------------------------------------------------
# Analytic cross-check of the flood-only limit
#
# In the flood-only limit the piecewise integral has a closed form; this
# independently validates GeneralModel's numerical quadrature.  With
# R = (lambda_F - lambda_bg) / lambda_bg, T = present, t_F the Flood time,
# formation time t_f = T - true_age, and a = max(t_f, t_F):
#
#   secular = (a - t_f) + (T - a)
#             + (R / k_F) * (exp(-k_F (a - t_F)) - exp(-k_F (T - t_F)))
# ----------------------------------------------------------------------------

def analytic_flood_only_secular_age(true_age, lambda_F, k_F, t_F,
                                    lambda_bg=1.0, present_time=AGE_OF_EARTH):
    R = (lambda_F - lambda_bg) / lambda_bg
    t_f = present_time - true_age
    a = max(t_f, t_F)
    return ((a - t_f) + (present_time - a)
            + (R / k_F) * (np.exp(-k_F * (a - t_F))
                           - np.exp(-k_F * (present_time - t_F))))


@pytest.mark.parametrize("lambda_F, k_F, t_F", [
    (1e5, 8.04e-3, 1656),
    (POSTERIOR_LAMBDA_F, POSTERIOR_K_F, 1656),
    (5365205.470625984, 0.009917296248264706, 732),
])
@pytest.mark.parametrize("true_age", [50, 1000, 3000, 4400, 5500, AGE_OF_EARTH])
def test_flood_only_matches_analytic_solution(lambda_F, k_F, t_F, true_age):
    model = GeneralModel.flood_only(lambda_F=lambda_F, k_F=k_F, t_F=t_F)
    expected = analytic_flood_only_secular_age(true_age, lambda_F, k_F, t_F)
    # compute_integral now evaluates this integral in closed form rather than
    # by quadrature, so it should agree with the independent analytic
    # expression above to near machine precision.  The old 2e-3 tolerance
    # existed only to accommodate quad's misplacement of the Flood spike.
    assert model.forward_age(true_age) == pytest.approx(expected, rel=1e-12)
