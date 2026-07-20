import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Rectangle
import os
from typing import List, Tuple, Dict
from scipy import stats


def load_mcmc_results(output_dir: str = 'mcmc_output_fixed') -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Load MCMC results from saved files."""
    # Load samples (shape: n_samples, n_params)
    samples = np.loadtxt(f'{output_dir}/samples.txt')

    # Load log probabilities; prefer per-chain log_probs_per_chain if available.
    log_probs_path = f'{output_dir}/log_probs_per_chain.txt'
    if os.path.exists(log_probs_path):
        log_probs_per_chain = np.loadtxt(log_probs_path)
    else:
        log_probs_per_chain = np.loadtxt(f'{output_dir}/log_probs.txt')

    # Load parameter names
    with open(f'{output_dir}/param_names.txt', 'r') as f:
        param_names = [line.strip() for line in f.readlines()]

    return samples, log_probs_per_chain, param_names


def infer_walkers_from_flat_chain(samples: np.ndarray, log_probs_flat: np.ndarray,
                                   min_steps: int = 10, max_walkers: int = 200):
    """Infer a plausible n_walkers and n_steps from flattened MCMC output."""
    total_samples = samples.shape[0]
    ndim = samples.shape[1]

    if log_probs_flat.ndim != 1 or log_probs_flat.shape[0] != total_samples:
        return 1, total_samples

    candidates = []
    for w in range(1, min(max_walkers, total_samples) + 1):
        if total_samples % w != 0:
            continue
        n_steps = total_samples // w
        if w >= max(2, 2 * ndim) and n_steps >= min_steps:
            candidates.append((w, n_steps))

    if candidates:
        # Prefer the largest walker count under the assumed limit.
        return max(candidates, key=lambda x: x[0])

    return 1, total_samples


def create_custom_corner_plot(samples: np.ndarray, param_names: List[str],
                            prior_means: Dict[str, float] = None, 
                            prior_sigmas: Dict[str, float] = None,
                            output_dir: str = 'mcmc_output_fixed'):
    """Create a custom corner plot with nice styling and prior distributions."""
    n_params = len(param_names)
    fig = plt.figure(figsize=(3*n_params, 3*n_params))

    # Create gridspec for the corner plot
    gs = gridspec.GridSpec(n_params, n_params, hspace=0.1, wspace=0.1)

    # Color scheme
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

    for i in range(n_params):
        for j in range(n_params):
            ax = fig.add_subplot(gs[i, j])

            if i == j:
                # Diagonal: histograms
                data = samples[:, i]
                param_name = param_names[i]
                
                # Set xlim first
                xlim = np.percentile(data, [1, 99])
                ax.set_xlim(xlim)
                
                # Plot histogram
                ax.hist(data, bins=30, density=True, alpha=0.7,
                       color=colors[i % len(colors)], edgecolor='black', linewidth=0.5)

                # Plot prior distribution if available
                if prior_means and prior_sigmas and param_name in prior_means and param_name in prior_sigmas:
                    x_prior = np.linspace(xlim[0], xlim[1], 1000)
                    prior_pdf = stats.norm.pdf(x_prior, prior_means[param_name], prior_sigmas[param_name])
                    ax.plot(x_prior, prior_pdf, 'k--', linewidth=2, alpha=0.8, label='Prior')

                # Add mean and std lines
                mean_val = np.mean(data)
                std_val = np.std(data)
                ax.axvline(mean_val, color='red', linestyle='--', linewidth=1, alpha=0.8)
                ax.axvline(mean_val - std_val, color='red', linestyle=':', linewidth=1, alpha=0.6)
                ax.axvline(mean_val + std_val, color='red', linestyle=':', linewidth=1, alpha=0.6)

                # Formatting
                if i < n_params - 1:
                    ax.set_xticklabels([])
                ax.set_yticklabels([])
                ax.set_ylabel('Density', fontsize=10)
                ax.tick_params(axis='both', which='major', labelsize=8)

            elif i > j:
                # Lower triangle: 2D histograms
                x_data = samples[:, j]
                y_data = samples[:, i]

                # Create 2D histogram
                hist, xedges, yedges = np.histogram2d(x_data, y_data, bins=30)
                hist = hist.T  # Transpose for correct orientation

                # Plot with nice colors
                im = ax.imshow(hist, extent=[xedges[0], xedges[-1], yedges[0], yedges[-1]],
                              origin='lower', aspect='auto', cmap='Blues', alpha=0.8)

                # Add contour lines
                levels = np.percentile(hist.flatten()[hist.flatten() > 0], [68, 95])
                ax.contour(hist, levels=levels, extent=[xedges[0], xedges[-1], yedges[0], yedges[-1]],
                          colors='red', linewidths=1, alpha=0.7)

            else:
                # Upper triangle: empty
                ax.set_visible(False)

            # Set axis labels
            if i == n_params - 1:
                ax.set_xlabel(param_names[j], fontsize=12)
            if j == 0 and i > 0:
                ax.set_ylabel(param_names[i], fontsize=12)

    # Add title
    fig.suptitle('MCMC Parameter Posterior Distributions', fontsize=16, y=0.95)

    # Save the plot
    plt.savefig(f'{output_dir}/custom_corner_plot.png', dpi=300, bbox_inches='tight')
    plt.close()

    print(f'Custom corner plot saved to {output_dir}/custom_corner_plot.png')


def create_custom_trace_plot(log_probs_per_chain: np.ndarray, param_names: List[str],
                           output_dir: str = 'mcmc_output_fixed'):
    """Create custom trace plots for each parameter and log probability."""
    n_params = len(param_names)

    # Load samples to get parameter traces
    samples, _, _ = load_mcmc_results(output_dir)

    if log_probs_per_chain.ndim == 1:
        # Flat log probabilities from legacy save format: infer walkers and steps automatically.
        n_walkers, n_steps = infer_walkers_from_flat_chain(samples, log_probs_per_chain)
        log_probs_per_chain = log_probs_per_chain.reshape(n_steps, n_walkers)
    else:
        n_steps, n_walkers = log_probs_per_chain.shape

    # Reshape samples to (n_steps, n_walkers, n_params)
    samples_per_chain = samples.reshape(n_steps, n_walkers, n_params)

    # Create figure with subplots
    fig, axes = plt.subplots(n_params + 1, 1, figsize=(12, 4*(n_params + 1)),
                           sharex=True)

    # Colors for different chains
    colors = plt.cm.tab10(np.linspace(0, 1, n_walkers))

    # Plot log probability traces
    ax = axes[0]
    for walker in range(min(n_walkers, 10)):  # Plot max 10 chains to avoid clutter
        ax.plot(log_probs_per_chain[:, walker], color=colors[walker],
               alpha=0.7, linewidth=1, label=f'Chain {walker}')
    ax.set_ylabel('Log Probability', fontsize=12)
    ax.set_title('Log Probability Traces', fontsize=14)
    ax.grid(True, alpha=0.3)
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
    ax.tick_params(axis='both', which='major', labelsize=10)

    # Plot parameter traces
    for param_idx in range(n_params):
        ax = axes[param_idx + 1]
        param_name = param_names[param_idx]

        for walker in range(min(n_walkers, 10)):  # Plot max 10 chains
            ax.plot(samples_per_chain[:, walker, param_idx],
                   color=colors[walker], alpha=0.7, linewidth=1)

        ax.set_ylabel(f'log({param_name})', fontsize=12)
        ax.set_title(f'{param_name} Trace', fontsize=14)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis='both', which='major', labelsize=10)

    # Set x-label for bottom plot
    axes[-1].set_xlabel('MCMC Step', fontsize=12)

    # Overall title
    fig.suptitle('MCMC Chain Traces', fontsize=16, y=0.98)

    # Adjust layout
    plt.tight_layout()
    plt.subplots_adjust(top=0.93, right=0.85)

    # Save the plot
    plt.savefig(f'{output_dir}/custom_trace_plot.png', dpi=300, bbox_inches='tight')
    plt.close()

    print(f'Custom trace plot saved to {output_dir}/custom_trace_plot.png')


def create_summary_statistics(samples: np.ndarray, param_names: List[str],
                            output_dir: str = 'mcmc_output_fixed'):
    """Create and save summary statistics."""
    summary = []

    for i, param_name in enumerate(param_names):
        data = samples[:, i]
        mean_val = np.mean(data)
        median_val = np.median(data)
        std_val = np.std(data)
        q16, q50, q84 = np.percentile(data, [16, 50, 84])

        summary.append({
            'parameter': param_name,
            'mean': mean_val,
            'median': median_val,
            'std': std_val,
            '16%': q16,
            '50%': q50,
            '84%': q84
        })

    # Save to text file
    with open(f'{output_dir}/summary_statistics.txt', 'w') as f:
        f.write("MCMC Summary Statistics\n")
        f.write("=" * 50 + "\n\n")

        for stat in summary:
            f.write(f"Parameter: {stat['parameter']}\n")
            f.write(f"  Mean:     {stat['mean']:.4f}\n")
            f.write(f"  Median:   {stat['median']:.4f}\n")
            f.write(f"  Std:      {stat['std']:.4f}\n")
            f.write(f"  16%:      {stat['16%']:.4f}\n")
            f.write(f"  50%:      {stat['50%']:.4f}\n")
            f.write(f"  84%:      {stat['84%']:.4f}\n")
            f.write("\n")

    print(f'Summary statistics saved to {output_dir}/summary_statistics.txt')

    return summary


def main():
    """Create custom plots from MCMC results."""
    output_dir = 'mcmc_output'

    if not os.path.exists(output_dir):
        print(f"Error: Output directory '{output_dir}' not found.")
        return

    # Load the results
    samples, log_probs_per_chain, param_names = load_mcmc_results(output_dir)

    # Define priors for the fixed model (from run_riag_mcmc_fixed.py)
    prior_means = {
        'lambda_F': 6,
        'k_F': -3,
    }
    prior_sigmas = {
        'lambda_F': 3,
        'k_F': 3,
    }

    # Create custom plots
    create_custom_corner_plot(samples, param_names, prior_means, prior_sigmas, output_dir)
    create_custom_trace_plot(log_probs_per_chain, param_names, output_dir)

    # Create summary statistics
    summary = create_summary_statistics(samples, param_names, output_dir)

    # Print summary to console
    print("\nMCMC Analysis Summary:")
    print("=" * 50)
    for stat in summary:
        print(f"{stat['parameter']}: {stat['median']:.4f} +{stat['84%']-stat['median']:.4f} -{stat['median']-stat['16%']:.4f}")


if __name__ == '__main__':
    main()