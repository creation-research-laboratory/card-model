"""
Tests for deterministic calibration.

The solved values are pinned against the ones recorded in todo.md on
2026-07-11 and previously computed by the standalone example scripts, so
moving the solve into the package is verifiably behavior-preserving.
"""

import dataclasses

import pytest

from card import FLOOD_AGE, ICE_AGE_END_AGE, solve_flood_only, solve_lambda_F
from card.calibrate import solve_flood_rate
from card.chronology import DEFAULT_CHRONOLOGY, Chronology

FLOOD_SECULAR = 541e6
ICE_AGE_SECULAR = 12e3


# ----------------------------------------------------------------------------
# Fixed-k_PF solve: one pair, one unknown
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("flood_ybp, k_PF, expected_lambda_F", [
    (5324, 0.0097, 5197236.175992864),
    (4374, 0.0124, 6626182.116554722),
])
def test_fixed_kf_matches_recorded_solutions(flood_ybp, k_PF, expected_lambda_F):
    result = solve_lambda_F(flood_age=flood_ybp,
                            flood_secular_age=FLOOD_SECULAR, k_PF=k_PF)
    assert result.lambda_F == pytest.approx(expected_lambda_F, rel=1e-9)
    assert result.k_PF == k_PF
    assert result.max_abs_residual < 1e-12


def test_fixed_kf_result_carries_a_working_model():
    result = solve_lambda_F(flood_age=4374, flood_secular_age=FLOOD_SECULAR,
                            k_PF=0.0124)
    assert result.model.forward_age(4374) == pytest.approx(FLOOD_SECULAR,
                                                           rel=1e-9)


def test_unreachable_target_is_rejected():
    """A secular age below the young age itself cannot be produced: the model
    can only ever make rocks look older."""
    with pytest.raises(ValueError, match="No lambda_F in"):
        solve_lambda_F(flood_age=4400, flood_secular_age=100.0, k_PF=1e-2)


@pytest.mark.parametrize("bad_secular", [0.0, -1.0])
def test_nonpositive_secular_age_is_rejected(bad_secular):
    with pytest.raises(ValueError, match="must be positive"):
        solve_lambda_F(flood_age=4400, flood_secular_age=bad_secular, k_PF=1e-2)


# ----------------------------------------------------------------------------
# Joint solve: two pairs, two unknowns
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("flood_ybp, ice_ybp, expected_lambda_F, expected_k_PF", [
    (5324, 4200, 5312542.703863794, 0.009917339712746347),
    (4374, 3500, 6761171.8507356495, 0.012655812042011749),
])
def test_joint_solve_matches_recorded_solutions(flood_ybp, ice_ybp,
                                                expected_lambda_F, expected_k_PF):
    result = solve_flood_only(flood_age=flood_ybp,
                              flood_secular_age=FLOOD_SECULAR,
                              second_age=ice_ybp,
                              second_secular_age=ICE_AGE_SECULAR)
    assert result.lambda_F == pytest.approx(expected_lambda_F, rel=1e-9)
    assert result.k_PF == pytest.approx(expected_k_PF, rel=1e-9)


def test_joint_solve_honors_both_constraints_exactly():
    result = solve_flood_only(flood_age=5324, flood_secular_age=FLOOD_SECULAR,
                              second_age=4200,
                              second_secular_age=ICE_AGE_SECULAR)
    assert result.max_abs_residual < 1e-9
    assert result.model.forward_age(5324) == pytest.approx(FLOOD_SECULAR, rel=1e-9)
    assert result.model.forward_age(4200) == pytest.approx(ICE_AGE_SECULAR, rel=1e-9)


def test_joint_solve_works_on_the_default_chronology():
    """The 2-D fsolve this replaced diverged to lambda_F ~ 1e-8 here, because
    its hardcoded initial guess suited a different chronology.  The bracketed
    solve has no guess to get wrong."""
    result = solve_flood_only(flood_age=FLOOD_AGE,
                              flood_secular_age=FLOOD_SECULAR,
                              second_age=ICE_AGE_END_AGE,
                              second_secular_age=11.7e3)
    assert result.lambda_F == pytest.approx(3.204607e6, rel=1e-3)
    assert result.k_PF == pytest.approx(5.95883e-3, rel=1e-3)
    assert result.max_abs_residual < 1e-9


def test_joint_solve_rejects_events_in_the_wrong_order():
    with pytest.raises(ValueError, match="more recent than"):
        solve_flood_only(flood_age=2556, flood_secular_age=FLOOD_SECULAR,
                         second_age=4400, second_secular_age=ICE_AGE_SECULAR)


def test_inconsistent_constraints_report_clearly():
    """Two pairs that no k_PF can satisfy should say so, not return nonsense."""
    with pytest.raises(ValueError, match="No k_PF in"):
        solve_flood_only(flood_age=4400, flood_secular_age=FLOOD_SECULAR,
                         second_age=2556, second_secular_age=1e9)


# ----------------------------------------------------------------------------
# Chronology awareness
# ----------------------------------------------------------------------------

def test_flood_age_outside_the_chronology_is_rejected():
    with pytest.raises(ValueError, match="It is an\n?\\s*AGE|outside"):
        solve_lambda_F(flood_age=99999, flood_secular_age=FLOOD_SECULAR,
                       k_PF=1e-2)


def test_calibration_is_invariant_to_the_age_of_the_earth():
    """Holding the Flood's AGE fixed, moving Day 1 of Creation earlier must not
    change the answer.

    In the flood-only limit lambda depends on ``t - t_F``, and the integral for
    a rock formed at the Flood spans exactly flood_age years, so nothing before
    the Flood enters it.  A different age_of_earth shifts the Flood's DATE but
    leaves the physics — and therefore lambda_F — untouched.
    """
    older = dataclasses.replace(DEFAULT_CHRONOLOGY, age_of_earth=7000)
    base = solve_lambda_F(FLOOD_AGE, FLOOD_SECULAR, 1e-2)
    variant = solve_lambda_F(FLOOD_AGE, FLOOD_SECULAR, 1e-2, chronology=older)

    assert variant.flood_date != base.flood_date          # 2600 vs 1656
    assert variant.lambda_F == pytest.approx(base.lambda_F, rel=1e-12)
    assert variant.max_abs_residual < 1e-12


def test_flood_age_barely_moves_lambda_F_once_the_exponential_saturates():
    """With ``k_PF * flood_age >> 1`` the relaxation term has decayed to nothing
    by the present, so the Flood constraint collapses to
    ``lambda_F ~ secular_age / (n + 1/k_PF)`` and depends only weakly on
    exactly when the Flood was.

    Here ``k_PF * flood_age`` is ~50, so moving the Flood by 950 years shifts
    lambda_F by about two parts per million.  Worth knowing before reading
    meaning into small lambda_F differences between chronologies.

    The ``n`` in that expression is the Flood year, which contributes
    ``lambda_F * n`` of apparent age directly.  Against ``1/k_PF = 100`` years
    of relaxation it is a 1% correction — small, but far larger than the
    chronology shift this test is about, so it belongs in the expression rather
    than in the tolerance.
    """
    earlier = solve_lambda_F(5324, FLOOD_SECULAR, 1e-2)
    later = solve_lambda_F(4374, FLOOD_SECULAR, 1e-2)

    assert earlier.lambda_F != later.lambda_F          # they do differ...
    assert earlier.lambda_F == pytest.approx(later.lambda_F, rel=1e-4)  # ...barely
    assert earlier.lambda_F == pytest.approx(
        FLOOD_SECULAR / (1.0 + 1.0 / 1e-2), rel=1e-3)


def test_lambda_F_scales_with_k_PF():
    """The strong dependence is on k_PF: in the saturated regime lambda_F is
    nearly proportional to it, so a faster relaxation needs a proportionally
    more intense Flood to reach the same secular age.

    Nearly, not exactly: the Flood year contributes ``lambda_F * n`` whatever
    k_PF is, so the ratio is ``(n + 1/k_PF) / (n + 1/2k_PF)`` = 1.98 rather
    than 2.  Pinned against that expression, which is exact.
    """
    slow = solve_lambda_F(FLOOD_AGE, FLOOD_SECULAR, 1e-2)
    fast = solve_lambda_F(FLOOD_AGE, FLOOD_SECULAR, 2e-2)
    expected_ratio = (1.0 + 1.0 / 1e-2) / (1.0 + 1.0 / 2e-2)
    assert fast.lambda_F / slow.lambda_F == pytest.approx(expected_ratio,
                                                          rel=1e-3)
    assert 1.9 < fast.lambda_F / slow.lambda_F < 2.0




# ---------------------------------------------------------------------------
# Three pairs: the in-Flood relaxation becomes the third unknown
#
# The Flood's *length* is no longer available as an unknown — it is one year,
# from the chronology — so what absorbs the third constraint is k_F, the rate
# at which lambda falls across that year.
# ---------------------------------------------------------------------------

PC_C_SECULAR = 541e6
KPG_SECULAR = 66e6
ICE_11500 = 11500.0


@pytest.fixture
def three_pair_solve():
    return solve_flood_rate(PC_C_SECULAR, KPG_SECULAR, ICE_11500)


def test_three_pair_solve_honors_all_three_exactly(three_pair_solve):
    """Three equations, three unknowns, so nothing is traded off."""
    assert three_pair_solve.max_abs_residual < 1e-12
    assert len(three_pair_solve.residuals) == 3


def test_three_pair_solve_matches_recorded_solution(three_pair_solve):
    """Pinned so a change to the model or the solver shows up here."""
    assert three_pair_solve.lambda_F == pytest.approx(4.5433185e9, rel=1e-5)
    assert three_pair_solve.k_F == pytest.approx(9.5642096, rel=1e-5)
    assert three_pair_solve.k_PF == pytest.approx(4.8325318e-3, rel=1e-5)
    assert three_pair_solve.lambda_F2 == pytest.approx(318926.84, rel=1e-5)


def test_three_pair_solve_reproduces_each_target(three_pair_solve):
    """The residuals are relative; check the absolute ages they stand for."""
    model = three_pair_solve.model
    present = DEFAULT_CHRONOLOGY.present_date

    assert model.forward_age(
        DEFAULT_CHRONOLOGY.flood_start_age, present
    ) == pytest.approx(PC_C_SECULAR, rel=1e-12)
    assert model.forward_age(
        DEFAULT_CHRONOLOGY.flood_end_age, present
    ) == pytest.approx(KPG_SECULAR, rel=1e-12)
    assert model.forward_age(
        DEFAULT_CHRONOLOGY.ice_age_end_age, present
    ) == pytest.approx(ICE_11500, rel=1e-12)


def test_three_pair_solve_keeps_the_flood_one_year(three_pair_solve):
    """The whole point: three pairs honored without stretching the Flood."""
    assert three_pair_solve.flood_duration == pytest.approx(1.0)
    params = three_pair_solve.model.params
    assert params.t_F2 - params.t_F == pytest.approx(1.0)


def test_three_pair_solve_falls_across_the_flood(three_pair_solve):
    """lambda decays monotonically from lambda_F to lambda_F2 across the year."""
    model = three_pair_solve.model
    params = model.params
    inside = [params.t_F + f for f in (1e-9, 0.25, 0.5, 0.75, 1.0)]
    rates = [model.lambda_func(t) for t in inside]

    assert rates == sorted(rates, reverse=True)
    assert rates[0] == pytest.approx(three_pair_solve.lambda_F, rel=1e-6)
    assert rates[-1] == pytest.approx(three_pair_solve.lambda_F2, rel=1e-12)
    assert three_pair_solve.lambda_F2 < three_pair_solve.lambda_F


def test_three_pair_solve_is_continuous_at_the_flood_end(three_pair_solve):
    """The continuity assumption is what makes this a 3x3 rather than a 4x4."""
    model = three_pair_solve.model
    t_F2 = model.params.t_F2
    assert model.lambda_func(t_F2 - 1e-9) == pytest.approx(
        model.lambda_func(t_F2 + 1e-9), rel=1e-6)


def test_three_pair_solve_still_steps_at_the_onset(three_pair_solve):
    """lambda jumps *up* at t_F; that discontinuity is the Flood's onset."""
    model = three_pair_solve.model
    t_F = model.params.t_F
    assert model.lambda_func(t_F) == pytest.approx(1.0)
    assert model.lambda_func(t_F + 1e-9) > 1e6


def test_in_flood_integral_supplies_the_gap_between_the_two_contacts(
        three_pair_solve):
    """The onset is older than the end by exactly the in-Flood integral.

    This is the identity the solve is built on, so it is worth pinning
    independently of the solver that used it.
    """
    model = three_pair_solve.model
    integral = model.compute_integral(model.params.t_F, model.params.t_F2)
    assert integral == pytest.approx(PC_C_SECULAR - KPG_SECULAR, rel=1e-9)


def test_three_pair_solve_rejects_a_post_flood_contact_that_is_older():
    """The Flood's end is later than its onset, so it must appear younger."""
    with pytest.raises(ValueError, match="must be younger"):
        solve_flood_rate(66e6, 541e6, ICE_11500)


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_three_pair_solve_rejects_nonpositive_secular_ages(bad):
    with pytest.raises(ValueError, match="must be positive"):
        solve_flood_rate(PC_C_SECULAR, KPG_SECULAR, bad)


def test_three_pair_solve_rejects_a_zero_length_flood():
    """With no Flood interval the first two pairs collapse onto one another."""
    instant = Chronology(age_of_earth=6056, flood_start_date=1656,
                         flood_end_date=1656, ice_age_end_date=3500)
    with pytest.raises(ValueError, match="no length"):
        solve_flood_rate(PC_C_SECULAR, KPG_SECULAR, ICE_11500,
                         chronology=instant)


def test_three_pair_solve_reports_an_unreachable_gap():
    """Two contacts too close together cannot be separated by any k_F.

    The in-Flood integral is smallest at k_F = 0, where it is lambda_F2 * n, so
    a gap below that is not reachable however the rate is shaped.
    """
    with pytest.raises(ValueError, match="even a Flood that never relaxes"):
        solve_flood_rate(KPG_SECULAR * 1.000001, KPG_SECULAR, ICE_11500)


def test_three_pair_solve_follows_the_chronology():
    """A different timeline is a different answer, not the same one relabelled."""
    septuagint = Chronology(age_of_earth=7500, flood_start_date=2176,
                            flood_end_date=2177, ice_age_end_date=3300)
    result = solve_flood_rate(PC_C_SECULAR, KPG_SECULAR, ICE_11500,
                              chronology=septuagint)
    assert result.max_abs_residual < 1e-12
    assert result.k_F != solve_flood_rate(
        PC_C_SECULAR, KPG_SECULAR, ICE_11500).k_F


def test_a_nearer_post_flood_contact_needs_a_gentler_flood():
    """N/Q asks the Flood year to carry more, so lambda must fall less steeply.

    Picking a *younger* post-Flood boundary widens the gap the Flood integral
    has to supply, and the only way to widen it is a larger lambda_F — reached
    here through a larger k_F, since continuity ties the two together.
    """
    kpg = solve_flood_rate(PC_C_SECULAR, KPG_SECULAR, ICE_11500)
    nq = solve_flood_rate(PC_C_SECULAR, 2.58e6, ICE_11500)
    assert nq.k_F > kpg.k_F
    assert nq.lambda_F > kpg.lambda_F
