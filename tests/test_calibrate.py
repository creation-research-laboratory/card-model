"""
Tests for deterministic calibration.

The solved values are pinned against the ones recorded in todo.md on
2026-07-11 and previously computed by the standalone example scripts, so
moving the solve into the package is verifiably behavior-preserving.
"""

import dataclasses

import pytest

from card import FLOOD_AGE, ICE_AGE_END_AGE, solve_flood_only, solve_lambda_F
from card.chronology import DEFAULT_CHRONOLOGY, Chronology

FLOOD_SECULAR = 541e6
ICE_AGE_SECULAR = 12e3


# ----------------------------------------------------------------------------
# Fixed-k_F solve: one pair, one unknown
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("flood_ybp, k_F, expected_lambda_F", [
    (5324, 0.0097, 5247649.357200022),
    (4374, 0.0124, 6708346.762400001),
])
def test_fixed_kf_matches_recorded_solutions(flood_ybp, k_F, expected_lambda_F):
    result = solve_lambda_F(flood_age=flood_ybp,
                            flood_secular_age=FLOOD_SECULAR, k_F=k_F)
    assert result.lambda_F == pytest.approx(expected_lambda_F, rel=1e-9)
    assert result.k_F == k_F
    assert result.max_abs_residual < 1e-12


def test_fixed_kf_result_carries_a_working_model():
    result = solve_lambda_F(flood_age=4374, flood_secular_age=FLOOD_SECULAR,
                            k_F=0.0124)
    assert result.model.forward_age(4374) == pytest.approx(FLOOD_SECULAR,
                                                           rel=1e-9)


def test_unreachable_target_is_rejected():
    """A secular age below the young age itself cannot be produced: the model
    can only ever make rocks look older."""
    with pytest.raises(ValueError, match="No lambda_F in"):
        solve_lambda_F(flood_age=4400, flood_secular_age=100.0, k_F=1e-2)


@pytest.mark.parametrize("bad_secular", [0.0, -1.0])
def test_nonpositive_secular_age_is_rejected(bad_secular):
    with pytest.raises(ValueError, match="must be positive"):
        solve_lambda_F(flood_age=4400, flood_secular_age=bad_secular, k_F=1e-2)


# ----------------------------------------------------------------------------
# Joint solve: two pairs, two unknowns
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("flood_ybp, ice_ybp, expected_lambda_F, expected_k_F", [
    (5324, 4200, 5365205.470625984, 0.009917296248264706),
    (4374, 3500, 6846690.80098783, 0.012655721177656678),
])
def test_joint_solve_matches_recorded_solutions(flood_ybp, ice_ybp,
                                                expected_lambda_F, expected_k_F):
    result = solve_flood_only(flood_age=flood_ybp,
                              flood_secular_age=FLOOD_SECULAR,
                              second_age=ice_ybp,
                              second_secular_age=ICE_AGE_SECULAR)
    assert result.lambda_F == pytest.approx(expected_lambda_F, rel=1e-9)
    assert result.k_F == pytest.approx(expected_k_F, rel=1e-9)


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
    assert result.lambda_F == pytest.approx(3.2237e6, rel=1e-3)
    assert result.k_F == pytest.approx(5.95882e-3, rel=1e-3)
    assert result.max_abs_residual < 1e-9


def test_joint_solve_rejects_events_in_the_wrong_order():
    with pytest.raises(ValueError, match="more recent than"):
        solve_flood_only(flood_age=2556, flood_secular_age=FLOOD_SECULAR,
                         second_age=4400, second_secular_age=ICE_AGE_SECULAR)


def test_inconsistent_constraints_report_clearly():
    """Two pairs that no k_F can satisfy should say so, not return nonsense."""
    with pytest.raises(ValueError, match="No k_F in"):
        solve_flood_only(flood_age=4400, flood_secular_age=FLOOD_SECULAR,
                         second_age=2556, second_secular_age=1e9)


# ----------------------------------------------------------------------------
# Chronology awareness
# ----------------------------------------------------------------------------

def test_flood_age_outside_the_chronology_is_rejected():
    with pytest.raises(ValueError, match="It is an\n?\\s*AGE|outside"):
        solve_lambda_F(flood_age=99999, flood_secular_age=FLOOD_SECULAR,
                       k_F=1e-2)


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
    """With ``k_F * flood_age >> 1`` the relaxation term has decayed to nothing
    by the present, so the Flood constraint collapses to
    ``lambda_F ~ k_F * secular_age`` and depends only weakly on exactly when
    the Flood was.

    Here ``k_F * flood_age`` is ~50, so moving the Flood by 950 years shifts
    lambda_F by about two parts per million.  Worth knowing before reading
    meaning into small lambda_F differences between chronologies.
    """
    earlier = solve_lambda_F(5324, FLOOD_SECULAR, 1e-2)
    later = solve_lambda_F(4374, FLOOD_SECULAR, 1e-2)

    assert earlier.lambda_F != later.lambda_F          # they do differ...
    assert earlier.lambda_F == pytest.approx(later.lambda_F, rel=1e-4)  # ...barely
    assert earlier.lambda_F == pytest.approx(1e-2 * FLOOD_SECULAR, rel=1e-3)


def test_lambda_F_scales_with_k_F():
    """The strong dependence is on k_F: in the saturated regime lambda_F is
    proportional to it, so a faster relaxation needs a proportionally more
    intense Flood to reach the same secular age."""
    slow = solve_lambda_F(FLOOD_AGE, FLOOD_SECULAR, 1e-2)
    fast = solve_lambda_F(FLOOD_AGE, FLOOD_SECULAR, 2e-2)
    assert fast.lambda_F == pytest.approx(2 * slow.lambda_F, rel=1e-3)
