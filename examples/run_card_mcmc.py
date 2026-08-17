"""
Main MCMC inversion: fit the flood-only limit of the General model.

Three matched date pairs constrain the three free rates:

  * rocks formed at the Flood's onset appear ~540 Myr old
    (the Precambrian-Cambrian boundary);
  * rocks formed as the Flood ended, one year later, appear ~66 Myr old
    (the K/Pg boundary);
  * rocks from the end of the Ice Age appear ~11.5 kyr old.

The middle pair is what earns the third rate.  A Flood whose lambda is constant
across the year separates its two ends by only ~3 Myr of apparent age, where
these anchors ask for ~474 Myr; letting lambda relax at `k_F` as the Flood runs
is what pulls them apart.  Pin `k_F` to 0 and drop that pair and you have the
old two-pair fit, which is still a valid special case — just not the default.

Writes the chain, figures and summary to `mcmc_output/`.

The same run is bundled as a config file, so

    card init myrun.yaml
    card fit myrun.yaml

produces the same outputs without editing Python.  This script is kept as the
readable, hardcoded version of what that config says.

For an exact deterministic answer to the same three constraints — no sampling,
no uncertainties — see `card.calibrate.solve_flood_rate` (or `card calibrate
myrun.yaml`); this script exists to get a *posterior*, which needs the
uncertainties.
"""

import math
import os

from card import (
    FLOOD_AGE,
    FLOOD_END_AGE,
    FLOOD_END_DATE,
    FLOOD_START_DATE,
    ICE_AGE_END_AGE,
    MCMCFitter,
    plot_age_comparison,
    plot_mcmc_corner,
    plot_mcmc_traces,
    solve_flood_rate,
    summarize_mcmc,
)


def main():
    n_steps = 20000
    n_burn = 5000
    out_dir = 'mcmc_output'
    os.makedirs(out_dir, exist_ok=True)

    # (young_AGE, secular_age, uncertainty).  These are AGEs — years before
    # present — not DATEs.  FLOOD_AGE is the Flood's onset, FLOOD_END_AGE its
    # end one year later.
    data = [
        (FLOOD_AGE, 540_000_000, 10_000_000.0),
        (FLOOD_END_AGE, 66_000_000, 100_000.0),
        (ICE_AGE_END_AGE, 11_500.0, 30.0),
    ]

    # Flood-only limit: no Creation-week acceleration.  k_F is absent, so it is
    # fitted along with the other two rates.  These are DATEs (years after
    # Creation), given in linear units — unlike the log10 priors below.
    fixed_params = {
        'lambda_c': 1.0,
        'k_c': 0.0,
        't_c': 1.0,
        't_F': FLOOD_START_DATE,
        't_F2': FLOOD_END_DATE,
    }

    # lambda_F and k_PF are log-scale parameters, so their priors are log10.
    # k_F is sampled LINEARLY: over a one-year Flood it lives within a few
    # multiples of 1/year, and its default of 0 has no log10.
    prior_means = {'lambda_F': 9.7, 'k_F': 9.6, 'k_PF': -2.3}
    prior_sigmas = {'lambda_F': 1.0, 'k_F': 5.0, 'k_PF': 1.0}

    fitter = MCMCFitter(
        data,
        prior_means=prior_means,
        prior_sigmas=prior_sigmas,
        fixed_params=fixed_params,
    )

    # Start the walkers at the exact solution to the same three constraints,
    # not at the prior means.  The two-pair form of this posterior has a second,
    # far local maximum (tiny lambda_F, k_PF small enough that the rate never
    # relaxes) that fits the tight Ice Age constraint while missing the Flood by
    # ~50 sigma; from the prior means about a quarter of the walkers fall into it
    # and never leave, contaminating every percentile.  MCMCFitter warns when
    # that happens.
    #
    # The guess is in sampling space and the three rates do not share one: log10
    # for lambda_F and k_PF, linear for k_F.  Order follows
    # fitter.free_param_names.
    exact = solve_flood_rate(540_000_000, 66_000_000, 11_500.0)
    initial_guess = [math.log10(exact.lambda_F), exact.k_F,
                     math.log10(exact.k_PF)]

    results = fitter.run_mcmc(n_walkers=32, n_steps=n_steps, burn_in=n_burn,
                              initial_guess=initial_guess)
    chain_path = fitter.save_results(results, os.path.join(out_dir, 'chain.h5'))
    print(f"Chain saved to {chain_path}")

    param_names = results['param_names']
    log_scale = results['log_scale']

    plot_mcmc_corner(
        results['samples'], param_names,
        prior_means=prior_means, prior_sigmas=prior_sigmas,
        log_scale=log_scale,
        out_file=os.path.join(out_dir, 'corner_plot.png'),
    )
    plot_mcmc_traces(
        results['chain'], results['log_prob_chain'], param_names,
        log_scale=log_scale,
        out_file=os.path.join(out_dir, 'trace_plot.png'),
    )
    summary = summarize_mcmc(
        results['samples'], param_names, log_scale=log_scale,
        out_file=os.path.join(out_dir, 'summary_statistics.txt'),
    )

    # Age-comparison figure from the posterior.  Note the `linear_` keys:
    # lambda_F and k_PF are sampled in log10, so the raw `mean`/`median` are
    # log10 values.  Passing those straight through — as this script used to —
    # plotted a lambda_F of ~6.5 instead of ~3.2e6.  k_F needs no conversion,
    # being sampled linearly, but it does need passing: leaving it out would
    # draw both curves at k_F = 0, which is not the model that was fitted.
    stats = {row['parameter']: row for row in summary}
    plot_age_comparison(
        lambda_F=stats['lambda_F']['linear_mean'],
        k_PF=stats['k_PF']['linear_mean'],
        k_F=stats['k_F']['linear_mean'],
        lambda_F_median=stats['lambda_F']['linear_median'],
        k_PF_median=stats['k_PF']['linear_median'],
        k_F_median=stats['k_F']['linear_median'],
        out_file=os.path.join(out_dir, 'age_comparison_posterior.png'),
    )

    print("\nMCMC summary")
    print("=" * 60)
    print(f"mean acceptance fraction: {results['acceptance_fraction']:.3f}")
    print(f"autocorrelation time:     {results['autocorr_time']}")
    if len(results['stuck_walkers']):
        print(f"WARNING: walkers {list(results['stuck_walkers'])} never joined "
              "the ensemble; the intervals below are contaminated.")
    for row in summary:
        print(f"{row['parameter']}: {row['linear_median']:.6g} "
              f"[{row['linear_16%']:.6g}, {row['linear_84%']:.6g}]")
    print(f"\nWrote chain.h5, corner_plot.png, trace_plot.png, "
          f"summary_statistics.txt and age_comparison_posterior.png to {out_dir}/")


if __name__ == '__main__':
    main()
