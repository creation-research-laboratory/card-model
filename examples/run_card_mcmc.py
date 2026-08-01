from card.decay_solver import AGE_OF_EARTH, FLOOD_START_DATE, FLOOD_END_DATE, FLOOD_AGE, ICE_AGE_END_AGE, plot_age_comparison
from card.card_mcmc import CARDMCMC
from card.create_custom_plots import load_mcmc_results, create_custom_corner_plot, create_custom_trace_plot, create_summary_statistics


def main():

    N_STEPS = 20000
    N_BURN = 5000
    OUT_DIR = 'mcmc_output'


    # Data points: (young_AGE, secular_age, uncertainty).
    # These are AGEs — years before present — not DATEs.  Constraint 1: rocks
    # formed at the Flood appear 540 Myr old.  Constraint 2: rocks from the
    # end of the Ice Age appear 11,500 yr old.
    data = [
        (FLOOD_AGE, 540_000_000, 10_000_000.0),
        (ICE_AGE_END_AGE, 11_500.0, 30.0),
    ]

    # Flood-only limit of the General model: no Creation-week acceleration.
    # These are DATEs — years after Creation — unlike the ages in `data`.
    fixed_params = {
        'lambda_c': 1.0,
        'k_c': 0.0,
        't_c': 1,
        't_F': FLOOD_START_DATE,
        't_F2': FLOOD_END_DATE,
    }


    prior_means = {
        'lambda_F': 6,
        'k_F': -3,
    }
    prior_sigmas = {
        'lambda_F': 1,
        'k_F': 1,
    }

    fitter = CARDMCMC(
        data,
        prior_means=prior_means,
        prior_sigmas=prior_sigmas,
        fixed_params=fixed_params,
    )
    
    results = fitter.run_mcmc(n_walkers=32, n_steps=N_STEPS, burn_in=N_BURN, output_dir=OUT_DIR)
    fitter.save_results(results, output_dir=OUT_DIR)
    # fitter.plot_convergence(results, output_dir=OUT_DIR)
    # fitter.plot_corner(results, output_dir=OUT_DIR)

    # Load the results
    samples, log_probs_per_chain, param_names = load_mcmc_results(output_dir=OUT_DIR)   

    # Create custom plots
    create_custom_corner_plot(samples, param_names, prior_means=prior_means, prior_sigmas=prior_sigmas, output_dir=OUT_DIR)
    create_custom_trace_plot(log_probs_per_chain, param_names, output_dir=OUT_DIR)

    # Create summary statistics
    summary = create_summary_statistics(samples, param_names, output_dir=OUT_DIR)

    # Plot age comparison using MCMC posterior mean and median estimates for lambda_F and k_F.
    posterior_stats = {stat['parameter']: stat for stat in summary}
    plot_age_comparison(
        lambda_F=posterior_stats['lambda_F']['mean'],
        k_F=posterior_stats['k_F']['mean'],
        lambda_F_median=posterior_stats['lambda_F']['median'],
        k_F_median=posterior_stats['k_F']['median'],
        out_file=f'{OUT_DIR}/age_comparison_plot_posterior_mean.png',
        show=False,
    )

    # Print summary to console
    print("\nMCMC Analysis Summary:")
    print("=" * 50)
    for stat in summary:
        print(f"{stat['parameter']}: {stat['median']:.4f} +{stat['84%']-stat['median']:.4f} -{stat['median']-stat['16%']:.4f}")


    print('MCMC inversion complete.')
    print('Saved files in mcmc_output/: samples.txt, log_probs.txt, acceptance.txt, param_names.txt, trace_plot.png, corner_plot.png, age_comparison_plot_posterior_mean.png')


if __name__ == '__main__':
    main()
