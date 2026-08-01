"""
Tests for the MCMC fitter and its HDF5 result format.

The MCMC itself was previously untested, so these are the first checks that
the sampler is wired up correctly: that the sampling space follows the
parameter spec, that fixed parameters really stay fixed, that invalid
parameters are rejected rather than sampled, and that a short run recovers
parameters it was given.
"""

import warnings

import numpy as np
import pytest

from card import (
    FLOOD_AGE,
    FLOOD_START_DATE,
    GeneralModel,
    ICE_AGE_END_AGE,
    MCMCFitter,
    load_results,
    solve_flood_only,
)

FLOOD_ONLY_FIXED = {
    'lambda_c': 1.0,
    'k_c': 0.0,
    't_c': 1.0,
    't_F': FLOOD_START_DATE,
    't_F2': FLOOD_START_DATE,
}

DATA = [
    (FLOOD_AGE, 541_000_000.0, 1e7),
    (ICE_AGE_END_AGE, 11_700.0, 100.0),
]


def make_fitter(**kwargs):
    kwargs.setdefault('fixed_params', FLOOD_ONLY_FIXED)
    kwargs.setdefault('prior_means', {'lambda_F': 6.5, 'k_F': -2.2})
    kwargs.setdefault('prior_sigmas', {'lambda_F': 1.0, 'k_F': 1.0})
    return MCMCFitter(DATA, **kwargs)


# ----------------------------------------------------------------------------
# Setup and the parameter spec
# ----------------------------------------------------------------------------

def test_free_parameters_come_from_the_spec():
    fitter = make_fitter()
    assert fitter.free_param_names == ('lambda_F', 'k_F')
    assert fitter.ndim == 2


def test_lambda_bg_is_fixed_without_being_named():
    """It is not fittable by definition, so the fitter must pin it itself."""
    fitter = make_fitter()
    assert fitter.fixed_params['lambda_bg'] == 1.0
    assert 'lambda_bg' not in fitter.free_param_names


def test_sampling_space_follows_the_spec():
    """lambda_F is log-scale so theta is log10; the times are linear."""
    fitter = make_fitter()
    params = fitter.theta_to_params(np.array([6.0, -2.0]))
    assert params.lambda_F == pytest.approx(1e6)
    assert params.k_F == pytest.approx(1e-2)
    assert params.t_F == FLOOD_START_DATE  # linear, straight through


def test_theta_round_trip():
    fitter = make_fitter()
    theta = np.array([6.3, -2.4])
    assert fitter.params_to_theta(fitter.theta_to_params(theta)) == \
        pytest.approx(theta)


def test_linear_time_sampling():
    """Times are sampled linearly, so a theta of 1656 means the year 1656."""
    fitter = MCMCFitter(DATA, fixed_params={'lambda_c': 1.0, 'k_c': 0.0,
                                            't_c': 1.0, 't_F2': 1656.0},
                        prior_means={'lambda_F': 6.5, 'k_F': -2.2,
                                     't_F': 1656.0},
                        prior_sigmas={'lambda_F': 1.0, 'k_F': 1.0,
                                      't_F': 100.0})
    index = fitter.free_param_names.index('t_F')
    theta = np.array([6.5, -2.2, 1656.0])
    assert fitter.theta_to_params(theta).t_F == pytest.approx(1656.0)
    assert index == 2


def test_unknown_fixed_parameter_is_rejected():
    with pytest.raises(ValueError, match="Unrecognized parameter"):
        MCMCFitter(DATA, fixed_params={'lambda_typo': 1.0})


def test_unknown_prior_name_is_rejected():
    with pytest.raises(ValueError, match="unknown parameter"):
        make_fitter(prior_means={'nope': 1.0})


def test_priors_default_from_the_spec():
    fitter = MCMCFitter(DATA, fixed_params=FLOOD_ONLY_FIXED)
    # lambda_F default is 1e5 and log-scale, so the prior centers on log10 -> 5
    assert fitter.prior_means['lambda_F'] == pytest.approx(5.0)


@pytest.mark.parametrize("bad_data, match", [
    ([], "at least one"),
    ([(100.0, 200.0)], "must be"),
    ([(100.0, 200.0, 0.0)], "positive"),
    ([(-1.0, 200.0, 1.0)], "negative age"),
])
def test_malformed_data_is_rejected(bad_data, match):
    with pytest.raises(ValueError, match=match):
        MCMCFitter(bad_data, fixed_params=FLOOD_ONLY_FIXED)


def test_everything_fixed_is_rejected():
    everything = dict(FLOOD_ONLY_FIXED, lambda_F=1e5, k_F=1e-2)
    with pytest.raises(ValueError, match="nothing to sample"):
        MCMCFitter(DATA, fixed_params=everything)


# ----------------------------------------------------------------------------
# Posterior
# ----------------------------------------------------------------------------

def test_invalid_parameters_get_zero_probability():
    """lambda_F below background violates validation, so the sampler must see
    -inf rather than an exception or a finite likelihood."""
    fitter = make_fitter()
    assert fitter.log_likelihood(np.array([-5.0, -2.0])) == -np.inf


def test_better_fit_has_higher_likelihood():
    fitter = make_fitter()
    truth = solve_flood_only(FLOOD_AGE, 541e6, ICE_AGE_END_AGE, 11.7e3)
    good = np.array([np.log10(truth.lambda_F), np.log10(truth.k_F)])
    worse = good + np.array([0.5, 0.5])
    assert fitter.log_likelihood(good) > fitter.log_likelihood(worse)


def test_present_time_defaults_to_the_package_chronology():
    assert make_fitter().present_time == 6056.0


def test_present_time_is_used_by_the_likelihood():
    """A fit under a different chronology has to measure forward ages against
    that chronology's present, not the default one — otherwise the data ages
    and the model ages come from two different timelines."""
    theta = np.array([6.5, -2.2])
    default = make_fitter().log_likelihood(theta)
    stretched = make_fitter(present_time=7000.0).log_likelihood(theta)
    assert default != stretched


def test_log_posterior_combines_prior_and_likelihood():
    fitter = make_fitter()
    theta = np.array([6.5, -2.2])
    assert fitter.log_posterior(theta) == pytest.approx(
        fitter.log_prior(theta) + fitter.log_likelihood(theta))


# ----------------------------------------------------------------------------
# Running
# ----------------------------------------------------------------------------

def test_too_few_walkers_is_rejected():
    fitter = make_fitter()
    with pytest.raises(ValueError, match="at least 2\\*ndim"):
        fitter.run_mcmc(n_walkers=2, n_steps=10, burn_in=0)


def test_short_run_recovers_the_calibrated_parameters():
    """A smoke test with a fixed seed: the chain should sit near the exact
    deterministic solution to the same two constraints."""
    np.random.seed(0)
    truth = solve_flood_only(FLOOD_AGE, 541e6, ICE_AGE_END_AGE, 11.7e3)
    fitter = make_fitter(
        prior_means={'lambda_F': np.log10(truth.lambda_F),
                     'k_F': np.log10(truth.k_F)},
        prior_sigmas={'lambda_F': 1.0, 'k_F': 1.0},
    )
    results = fitter.run_mcmc(n_walkers=16, n_steps=600, burn_in=200,
                              progress=False)

    assert results['chain'].shape == (600, 16, 2)
    assert results['log_prob_chain'].shape == (600, 16)
    assert results['samples'].shape == (600 * 16, 2)
    assert 0.0 < results['acceptance_fraction'] < 1.0

    median = np.median(results['samples'], axis=0)
    assert 10 ** median[0] == pytest.approx(truth.lambda_F, rel=0.5)
    assert 10 ** median[1] == pytest.approx(truth.k_F, rel=0.5)


# The tests below run 20-50 steps from the prior means purely to get an object
# of the right shape.  Chains that short genuinely have not converged, so the
# stuck-walker warning is correct and beside the point; it is silenced per test
# rather than globally, so a *new* warning still surfaces.
@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_fixed_parameters_never_move():
    np.random.seed(1)
    fitter = make_fitter()
    results = fitter.run_mcmc(n_walkers=8, n_steps=50, burn_in=0,
                              progress=False)
    for theta in results['samples'][::40]:
        params = fitter.theta_to_params(theta)
        assert params.t_F == FLOOD_START_DATE
        assert params.lambda_c == 1.0
        assert params.lambda_bg == 1.0


@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_results_record_the_sampling_space():
    np.random.seed(2)
    results = make_fitter().run_mcmc(n_walkers=8, n_steps=20, burn_in=0,
                                     progress=False)
    assert results['param_names'] == ['lambda_F', 'k_F']
    assert results['log_scale'] == [True, True]


# ----------------------------------------------------------------------------
# Randomness: per-run, never global
# ----------------------------------------------------------------------------

@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_the_same_seed_reproduces_a_run():
    first = make_fitter().run_mcmc(n_walkers=8, n_steps=30, burn_in=5,
                                   seed=1, progress=False)
    second = make_fitter().run_mcmc(n_walkers=8, n_steps=30, burn_in=5,
                                    seed=1, progress=False)
    np.testing.assert_array_equal(first['chain'], second['chain'])


@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_different_seeds_give_different_runs():
    first = make_fitter().run_mcmc(n_walkers=8, n_steps=30, burn_in=5,
                                   seed=1, progress=False)
    second = make_fitter().run_mcmc(n_walkers=8, n_steps=30, burn_in=5,
                                    seed=2, progress=False)
    assert not np.array_equal(first['chain'], second['chain'])


@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_a_seeded_run_ignores_the_global_numpy_rng():
    """The sampler must not read or write process-global random state.  Two
    fits in one process — two requests to a web service, two tabs of a GUI —
    would otherwise perturb each other, and any unrelated `np.random.seed` call
    would silently change a 'reproducible' run."""
    np.random.seed(11)
    first = make_fitter().run_mcmc(n_walkers=8, n_steps=30, burn_in=5,
                                   seed=7, progress=False)
    np.random.seed(9999)                       # someone else reseeds
    second = make_fitter().run_mcmc(n_walkers=8, n_steps=30, burn_in=5,
                                    seed=7, progress=False)
    np.testing.assert_array_equal(first['chain'], second['chain'])


@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_an_unseeded_run_does_not_disturb_the_global_rng():
    np.random.seed(5)
    before = np.random.random()
    np.random.seed(5)
    make_fitter().run_mcmc(n_walkers=8, n_steps=20, burn_in=0, progress=False)
    assert np.random.random() == before


def test_seed_and_rng_together_are_rejected():
    with pytest.raises(ValueError, match="either seed or rng"):
        make_fitter().run_mcmc(n_walkers=8, n_steps=10, burn_in=0,
                               seed=1, rng=np.random.default_rng(1),
                               progress=False)


@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_an_explicit_generator_is_honored():
    first = make_fitter().run_mcmc(n_walkers=8, n_steps=20, burn_in=0,
                                   rng=np.random.default_rng(3), progress=False)
    second = make_fitter().run_mcmc(n_walkers=8, n_steps=20, burn_in=0,
                                    rng=np.random.default_rng(3), progress=False)
    np.testing.assert_array_equal(first['chain'], second['chain'])


# ----------------------------------------------------------------------------
# Progress reporting and cancellation
# ----------------------------------------------------------------------------

@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_the_callback_sees_every_step_of_both_phases():
    """A GUI needs incremental progress; emcee's own bar writes to a terminal
    nobody is watching."""
    seen = []
    make_fitter().run_mcmc(n_walkers=8, n_steps=12, burn_in=4, seed=1,
                           progress=False, callback=seen.append)

    assert [p.phase for p in seen] == ['burn-in'] * 4 + ['sampling'] * 12
    assert [p.step for p in seen[:4]] == [1, 2, 3, 4]
    assert seen[-1].fraction == pytest.approx(1.0)
    assert 0.0 <= seen[-1].acceptance_fraction <= 1.0


@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_returning_false_from_the_callback_stops_the_run():
    """The cancel button.  The results must then describe the steps actually
    taken, not the steps requested."""
    def stop_at_five(progress):
        return not (progress.phase == 'sampling' and progress.step >= 5)

    results = make_fitter().run_mcmc(n_walkers=8, n_steps=100, burn_in=2,
                                     seed=1, progress=False,
                                     callback=stop_at_five)

    assert results['stopped_early'] is True
    assert results['n_steps'] == 5
    assert results['n_steps_requested'] == 100
    assert results['chain'].shape == (5, 8, 2)


@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_a_run_that_finishes_is_not_marked_stopped():
    results = make_fitter().run_mcmc(n_walkers=8, n_steps=10, burn_in=0,
                                     seed=1, progress=False,
                                     callback=lambda progress: True)
    assert results['stopped_early'] is False
    assert results['n_steps'] == results['n_steps_requested'] == 10


# ----------------------------------------------------------------------------
# Stuck-walker diagnostic
# ----------------------------------------------------------------------------

def test_a_trapped_walker_is_reported():
    """The main inversion's posterior has a far local maximum that swallows
    walkers permanently.  Their samples are non-convergence, not posterior
    mass, and they used to drag the reported 16th percentile of lambda_F from
    3.2e6 down to 5.4 with nothing said."""
    log_prob = np.full((100, 8), -1.0)
    log_prob[:, 3] = -1500.0          # trapped in the other mode

    with pytest.warns(UserWarning, match="never joined the ensemble"):
        stuck = MCMCFitter._find_stuck_walkers(log_prob)
    assert stuck.tolist() == [3]


def test_a_converged_ensemble_is_not_flagged():
    rng = np.random.default_rng(0)
    log_prob = rng.normal(-1.0, 0.5, size=(100, 8))
    with warnings.catch_warnings():
        warnings.simplefilter("error")   # any warning here fails the test
        assert MCMCFitter._find_stuck_walkers(log_prob).size == 0


@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_a_run_reports_its_stuck_walkers():
    np.random.seed(6)
    results = make_fitter().run_mcmc(n_walkers=8, n_steps=20, burn_in=0,
                                     progress=False)
    assert 'stuck_walkers' in results


def test_starting_at_the_exact_solution_converges():
    """`solve_flood_only` answers the same two constraints deterministically,
    so it is the right place to start the walkers — and starting there is what
    keeps them out of the far mode."""
    np.random.seed(7)
    truth = solve_flood_only(FLOOD_AGE, 541e6, ICE_AGE_END_AGE, 11.7e3)
    guess = [np.log10(truth.lambda_F), np.log10(truth.k_F)]
    results = make_fitter().run_mcmc(n_walkers=16, n_steps=300, burn_in=100,
                                     initial_guess=guess, progress=False)
    assert len(results['stuck_walkers']) == 0
    assert results['acceptance_fraction'] > 0.2


# ----------------------------------------------------------------------------
# HDF5 round trip
# ----------------------------------------------------------------------------

@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_results_round_trip_through_hdf5(tmp_path):
    np.random.seed(3)
    fitter = make_fitter()
    results = fitter.run_mcmc(n_walkers=8, n_steps=40, burn_in=0,
                              progress=False)
    path = str(tmp_path / "chain.h5")
    fitter.save_results(results, path)

    loaded = load_results(path)
    assert loaded['param_names'] == results['param_names']
    assert loaded['log_scale'] == results['log_scale']
    np.testing.assert_allclose(loaded['chain'], results['chain'])
    np.testing.assert_allclose(loaded['log_prob_chain'],
                               results['log_prob_chain'])
    assert loaded['n_walkers'] == 8


@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_saved_chain_keeps_walker_structure(tmp_path):
    """The old text format flattened the chain, so the plotting code had to
    guess the walker count back by factorizing the sample total.  HDF5 records
    it, so nothing downstream has to guess."""
    np.random.seed(4)
    results = make_fitter().run_mcmc(n_walkers=8, n_steps=25, burn_in=0,
                                     progress=False)
    path = str(tmp_path / "chain.h5")
    make_fitter().save_results(results, path)
    assert load_results(path)['chain'].shape == (25, 8, 2)


def test_loading_a_missing_file_says_so(tmp_path):
    with pytest.raises(FileNotFoundError, match="No MCMC results"):
        load_results(str(tmp_path / "absent.h5"))


@pytest.mark.filterwarnings("ignore:.*never joined the ensemble")
def test_hdf5_backend_streams_the_chain(tmp_path):
    """With backend_path emcee writes as it goes, so a long run is resumable
    and inspectable before it finishes."""
    np.random.seed(5)
    backend_path = str(tmp_path / "live.h5")
    results = make_fitter().run_mcmc(n_walkers=8, n_steps=30, burn_in=0,
                                     progress=False, backend_path=backend_path)
    import emcee
    backend = emcee.backends.HDFBackend(backend_path, read_only=True)
    assert backend.get_chain().shape == results['chain'].shape
