"""
Main MCMC inversion: fit the flood-only limit of the General model.

Two matched date pairs constrain the two free parameters:

  * rocks formed at the Flood appear ~540 Myr old;
  * rocks from the end of the Ice Age appear ~11.5 kyr old.

Writes the chain, figures and summary to `mcmc_output/`.

`examples/flood_only.yaml` is this same run as a config file, so

    card fit examples/flood_only.yaml

produces the same outputs without editing Python.  This script is kept as the
readable, hardcoded version of what that config says.

For an exact deterministic answer to the same two constraints — no sampling,
no uncertainties — see `card.calibrate.solve_flood_only` (or `card calibrate
examples/flood_only.yaml`); this script exists to get a *posterior*, which
needs the uncertainties.
"""

import os

from card import (
    FLOOD_AGE,
    FLOOD_END_DATE,
    FLOOD_START_DATE,
    ICE_AGE_END_AGE,
    MCMCFitter,
    plot_age_comparison,
    plot_mcmc_corner,
    plot_mcmc_traces,
    summarize_mcmc,
)


def main():
    n_steps = 20000
    n_burn = 5000
    out_dir = 'mcmc_output'
    os.makedirs(out_dir, exist_ok=True)

    # (young_AGE, secular_age, uncertainty).  These are AGEs — years before
    # present — not DATEs.
    data = [
        (FLOOD_AGE, 540_000_000, 10_000_000.0),
        (ICE_AGE_END_AGE, 11_500.0, 30.0),
    ]

    # Flood-only limit: no Creation-week acceleration, instantaneous Flood.
    # These are DATEs (years after Creation), given in linear units — unlike
    # the log10 priors below.
    fixed_params = {
        'lambda_c': 1.0,
        'k_c': 0.0,
        't_c': 1.0,
        't_F': FLOOD_START_DATE,
        't_F2': FLOOD_END_DATE,
    }

    # lambda_F and k_F are log-scale parameters, so their priors are log10.
    prior_means = {'lambda_F': 6.0, 'k_F': -3.0}
    prior_sigmas = {'lambda_F': 1.0, 'k_F': 1.0}

    fitter = MCMCFitter(
        data,
        prior_means=prior_means,
        prior_sigmas=prior_sigmas,
        fixed_params=fixed_params,
    )

    results = fitter.run_mcmc(n_walkers=32, n_steps=n_steps, burn_in=n_burn)
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
    # lambda_F and k_F are sampled in log10, so the raw `mean`/`median` are
    # log10 values.  Passing those straight through — as this script used to —
    # plotted a lambda_F of ~6.5 instead of ~3.2e6.
    stats = {row['parameter']: row for row in summary}
    plot_age_comparison(
        lambda_F=stats['lambda_F']['linear_mean'],
        k_F=stats['k_F']['linear_mean'],
        lambda_F_median=stats['lambda_F']['linear_median'],
        k_F_median=stats['k_F']['linear_median'],
        out_file=os.path.join(out_dir, 'age_comparison_posterior.png'),
    )

    print("\nMCMC summary")
    print("=" * 60)
    print(f"mean acceptance fraction: {results['acceptance_fraction']:.3f}")
    print(f"autocorrelation time:     {results['autocorr_time']}")
    for row in summary:
        print(f"{row['parameter']}: {row['linear_median']:.6g} "
              f"[{row['linear_16%']:.6g}, {row['linear_84%']:.6g}]")
    print(f"\nWrote chain.h5, corner_plot.png, trace_plot.png, "
          f"summary_statistics.txt and age_comparison_posterior.png to {out_dir}/")


if __name__ == '__main__':
    main()
