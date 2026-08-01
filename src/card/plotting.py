"""
Figure generation for CARD models.

This is the only module in the core that imports matplotlib, so keeping it
separate lets a caller use the models without pulling in a plotting stack —
which matters for a browser build or a lightweight service.

Library plotting rules observed here:

  * Never call ``matplotlib.use()``.  Selecting a backend is a process-wide
    side effect that belongs to the application, not the library.  An earlier
    version forced "Agg" on import, which silently overrode a host GUI's
    backend and made ``show=True`` a no-op.
  * Accept an optional ``ax`` so a GUI can draw into a canvas it owns.  When
    ``ax`` is given, the caller owns the figure: nothing is saved, shown, or
    closed.
"""

from itertools import product
from typing import Dict, List, Optional

import matplotlib.cm as cm
import matplotlib.pyplot as plt
import numpy as np

from .constants import (
    AGE_OF_EARTH,
    FLOOD_START_AGE,
    FLOOD_START_DATE,
    LAMBDA_BG,
)
from .models import ConstantDecayModel, GeneralModel, GeneralModelParams

__all__ = [
    "load_legacy_text_results",
    "plot_age_comparison",
    "plot_general_model_parameter_sweep",
    "plot_mcmc_corner",
    "plot_mcmc_traces",
    "summarize_mcmc",
]


def _finish(fig, ax, out_file, show, owns_figure):
    """Save/show/close only when this function created the figure."""
    if not owns_figure:
        return ax

    fig.tight_layout()
    if out_file:
        fig.savefig(out_file, dpi=180, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)
    return out_file


def plot_age_comparison(
    age_of_earth: float = AGE_OF_EARTH,
    n_points: int = 1000,
    out_file: str = "age_comparison_plot.png",
    show: bool = False,
    lambda_F: float = 5e5,
    k_F: float = 0.5e-2,
    lambda_F_median: Optional[float] = None,
    k_F_median: Optional[float] = None,
    flood_date: float = None,
    ax=None,
):
    """Compare secular age against young age for the constant and general models.

    Args:
        age_of_earth: Largest young AGE to plot, in years before present.
        n_points: Number of sample points between 0 and age_of_earth.
        out_file: Output filename for the figure.
        show: If True, display the figure (ignored when `ax` is given).
        lambda_F: Posterior mean lambda_F for the general model.
        k_F: Posterior mean k_F for the general model.
        lambda_F_median: Posterior median lambda_F; plotted if given with k_F_median.
        k_F_median: Posterior median k_F; plotted if given with lambda_F_median.
        flood_date: DATE of the Flood (default: the chronology's Flood date).
        ax: Optional existing axes to draw into.  When supplied the caller owns
            the figure and this returns the axes instead of a path.

    Returns:
        Path to the saved figure, or the axes when `ax` was supplied.
    """
    if flood_date is None:
        flood_date = FLOOD_START_DATE

    const_model = ConstantDecayModel(lambda_bg=LAMBDA_BG)
    general_model = GeneralModel.flood_only(lambda_F=lambda_F, k_F=k_F,
                                            t_F=flood_date)
    median_model = None
    if lambda_F_median is not None and k_F_median is not None:
        median_model = GeneralModel.flood_only(lambda_F=lambda_F_median,
                                               k_F=k_F_median, t_F=flood_date)

    flood_secular_age = general_model.forward_age(FLOOD_START_AGE)

    x = np.linspace(0, age_of_earth, n_points)
    y_const = np.array([const_model.forward_age(t) for t in x])
    y_general = np.array([general_model.forward_age(t) for t in x])

    owns_figure = ax is None
    if owns_figure:
        fig, ax = plt.subplots(figsize=(10, 6))
    else:
        fig = ax.get_figure()

    ax.semilogy(x, y_const, label="Constant decay", color="blue")
    ax.semilogy(x, y_general, label="Posterior mean general", color="green")
    if median_model is not None:
        y_median = np.array([median_model.forward_age(t) for t in x])
        ax.semilogy(x, y_median, label="Posterior median general",
                    color="purple", linestyle="--")
    ax.axvline(x=FLOOD_START_AGE, color="red", linestyle="--",
               label="Flood event")
    ax.axhline(y=flood_secular_age, color="purple", linestyle="--",
               label="Flood secular age")
    ax.set_xlabel("Young age (years before present)")
    ax.set_ylabel("Secular age (years)")
    ax.set_title("Secular age vs young age (0 to present)")
    ax.legend()
    ax.grid(True)

    return _finish(fig, ax, out_file, show, owns_figure)


def plot_general_model_parameter_sweep(
    base_params: Optional[GeneralModelParams] = None,
    vary_params: Optional[Dict[str, List[float]]] = None,
    age_of_earth: float = AGE_OF_EARTH,
    n_points: int = 1000,
    out_file: str = "general_model_sweep_plot.png",
    show: bool = False,
    ax=None,
):
    """Plot the age curve for several parameter combinations of the general model.

    Args:
        base_params: Baseline parameters; standard values are used if omitted.
        vary_params: ``{parameter_name: [values]}`` to sweep.  Valid names are
            the fields of GeneralModelParams.
        age_of_earth: Largest young AGE to plot, in years before present.
        n_points: Number of sample points between 0 and age_of_earth.
        out_file: Output filename for the figure.
        show: If True, display the figure (ignored when `ax` is given).
        ax: Optional existing axes to draw into.  When supplied the caller owns
            the figure and this returns the axes instead of a path.

    Returns:
        Path to the saved figure, or the axes when `ax` was supplied.

    Raises:
        ValueError: If `vary_params` names a parameter the model does not have.
    """
    if base_params is None:
        base_params = GeneralModelParams(
            lambda_c=1e3,
            lambda_F=1e5,
            lambda_bg=1.0,
            k_c=1e-1,
            k_F=8.04e-3,
            t_c=1,
            t_F=FLOOD_START_DATE,
            t_F2=FLOOD_START_DATE + 1,
        )

    if vary_params is None:
        vary_params = {
            'lambda_F': [1e5, 5e5, 1e6],
            'k_F': [2e-3, 5e-3, 8e-3],
        }

    base_dict = base_params.to_dict()
    unknown = set(vary_params) - set(base_dict)
    if unknown:
        raise ValueError(
            f"vary_params names unknown parameters {sorted(unknown)}; "
            f"expected any of {sorted(base_dict)}."
        )

    param_names = list(vary_params.keys())
    combinations = list(product(*vary_params.values()))
    colors = cm.viridis(np.linspace(0, 1, len(combinations)))

    x = np.linspace(0, age_of_earth, n_points)

    owns_figure = ax is None
    if owns_figure:
        fig, ax = plt.subplots(figsize=(12, 8))
    else:
        fig = ax.get_figure()

    const_model = ConstantDecayModel(lambda_bg=LAMBDA_BG)
    ax.semilogy(x, np.array([const_model.forward_age(t) for t in x]),
                label="Constant decay", color="blue")

    for i, combo in enumerate(combinations):
        params_dict = dict(base_dict)
        params_dict.update(dict(zip(param_names, combo)))
        model = GeneralModel(GeneralModelParams(**params_dict))

        y = np.array([model.forward_age(t) for t in x])

        label_parts = []
        for name, value in zip(param_names, combo):
            if value >= 1e3:
                label_parts.append(f"{name}={value:.0e}")
            elif value >= 1:
                label_parts.append(f"{name}={value:.1f}")
            else:
                label_parts.append(f"{name}={value:.2e}")

        ax.semilogy(x, y, color=colors[i], linewidth=2,
                    label=", ".join(label_parts))

    ax.axvline(x=FLOOD_START_AGE, color="red", linestyle="--", alpha=0.7,
               label="Flood event")
    ax.axhline(y=540e6, color="purple", linestyle="--", alpha=0.7,
               label="540 Myr secular age")

    ax.set_xlabel("Young age (years before present)")
    ax.set_ylabel("Secular age (years)")
    ax.set_title("General model parameter sweep: secular age vs young age")
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)

    return _finish(fig, ax, out_file, show, owns_figure)


# ============================================================================
# MCMC RESULT PLOTS
#
# Merged from the former create_custom_plots.py.  These take the results dict
# from card.inference directly, so the chain arrives with its (step, walker)
# structure intact.  The old versions read flattened text files and had to
# reconstruct the walker count by factorizing the sample total — see
# _infer_walkers_from_flat_chain, which now exists only to read those legacy
# files.
# ============================================================================

_CHAIN_COLORS = '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'


def _spec_label(name, log_scale=False):
    """LaTeX axis label for a parameter, from its spec when one exists."""
    specs = GeneralModelParams.specs()
    symbol = specs[name].symbol if name in specs else name
    body = rf"$\log_{{10}} {symbol}$" if log_scale else rf"${symbol}$"
    return body


def summarize_mcmc(samples, param_names, log_scale=None, out_file=None):
    """Summary statistics for each sampled parameter.

    Reports each parameter in **both** spaces: the sampling space the chain
    lives in, and linear model units.  The old version reported only the raw
    samples, which meant a caller reading `mean` for a log10-sampled parameter
    got ~6.5 where the model wanted ~3.2e6 — a mistake the shipped driver was
    actually making when feeding posterior values into the age-comparison plot.

    Args:
        samples: Flat chain, shape ``(n_samples, n_params)``.
        param_names: Parameter names matching the columns.
        log_scale: Per-parameter flags saying which columns are log10.
            Defaults to the model spec's flags.
        out_file: Optional path to write a text report to.

    Returns:
        List of per-parameter dicts.  Sampling-space keys are ``mean``,
        ``median``, ``std``, ``16%``, ``50%``, ``84%``; linear-space keys carry
        a ``linear_`` prefix.
    """
    samples = np.asarray(samples)
    if log_scale is None:
        specs = GeneralModelParams.specs()
        log_scale = [specs[n].log_scale if n in specs else False
                     for n in param_names]

    summary = []
    for i, name in enumerate(param_names):
        column = samples[:, i]
        q16, q50, q84 = np.percentile(column, [16, 50, 84])
        linear = 10.0 ** column if log_scale[i] else column
        lin16, lin50, lin84 = np.percentile(linear, [16, 50, 84])
        summary.append({
            'parameter': name,
            'log_scale': bool(log_scale[i]),
            'mean': float(np.mean(column)),
            'median': float(q50),
            'std': float(np.std(column)),
            '16%': float(q16), '50%': float(q50), '84%': float(q84),
            'linear_mean': float(np.mean(linear)),
            'linear_median': float(lin50),
            'linear_16%': float(lin16),
            'linear_84%': float(lin84),
        })

    if out_file:
        with open(out_file, 'w') as handle:
            handle.write("MCMC Summary Statistics\n")
            handle.write("=" * 60 + "\n\n")
            for stat in summary:
                space = "log10" if stat['log_scale'] else "linear"
                handle.write(f"Parameter: {stat['parameter']}  "
                             f"(sampled in {space})\n")
                handle.write(f"  sampled  median {stat['median']:.6g}  "
                             f"[{stat['16%']:.6g}, {stat['84%']:.6g}]\n")
                handle.write(f"  linear   median {stat['linear_median']:.6g}  "
                             f"[{stat['linear_16%']:.6g}, "
                             f"{stat['linear_84%']:.6g}]\n")
                handle.write(f"  mean     {stat['mean']:.6g} sampled / "
                             f"{stat['linear_mean']:.6g} linear\n\n")
    return summary


def plot_mcmc_corner(samples, param_names, prior_means=None, prior_sigmas=None,
                     log_scale=None, out_file='corner_plot.png', show=False):
    """Styled corner plot of the posterior, with priors overlaid.

    Args:
        samples: Flat chain, shape ``(n_samples, n_params)``.
        param_names: Parameter names matching the columns.
        prior_means: Optional prior centers, in sampling space.
        prior_sigmas: Optional prior widths, in sampling space.
        log_scale: Per-parameter log10 flags, for axis labels.
        out_file: Output filename.
        show: If True, display the figure.

    Returns:
        Path to the saved figure.
    """
    from scipy import stats

    samples = np.asarray(samples)
    n_params = len(param_names)
    if log_scale is None:
        specs = GeneralModelParams.specs()
        log_scale = [specs[n].log_scale if n in specs else False
                     for n in param_names]

    fig, axes = plt.subplots(n_params, n_params,
                             figsize=(3 * n_params, 3 * n_params),
                             squeeze=False)
    fig.subplots_adjust(hspace=0.1, wspace=0.1)

    for i in range(n_params):
        for j in range(n_params):
            ax = axes[i][j]

            if i == j:
                column = samples[:, i]
                xlim = np.percentile(column, [1, 99])
                ax.set_xlim(xlim)
                ax.hist(column, bins=30, density=True, alpha=0.7,
                        color=_CHAIN_COLORS[i % len(_CHAIN_COLORS)],
                        edgecolor='black', linewidth=0.5)

                name = param_names[i]
                if prior_means and prior_sigmas and name in prior_means \
                        and name in prior_sigmas:
                    grid = np.linspace(xlim[0], xlim[1], 400)
                    ax.plot(grid,
                            stats.norm.pdf(grid, prior_means[name],
                                           prior_sigmas[name]),
                            'k--', linewidth=2, alpha=0.8, label='Prior')

                mean, std = np.mean(column), np.std(column)
                ax.axvline(mean, color='red', linestyle='--', linewidth=1,
                           alpha=0.8)
                for edge in (mean - std, mean + std):
                    ax.axvline(edge, color='red', linestyle=':', linewidth=1,
                               alpha=0.6)
                ax.set_yticklabels([])

            elif i > j:
                hist, xedges, yedges = np.histogram2d(samples[:, j],
                                                      samples[:, i], bins=30)
                hist = hist.T
                extent = [xedges[0], xedges[-1], yedges[0], yedges[-1]]
                ax.imshow(hist, extent=extent, origin='lower', aspect='auto',
                          cmap='Blues', alpha=0.8)
                positive = hist.flatten()[hist.flatten() > 0]
                if positive.size:
                    ax.contour(hist, levels=np.percentile(positive, [68, 95]),
                               extent=extent, colors='red', linewidths=1,
                               alpha=0.7)
            else:
                ax.set_visible(False)

            if i < n_params - 1:
                ax.set_xticklabels([])
            if i == n_params - 1:
                ax.set_xlabel(_spec_label(param_names[j], log_scale[j]),
                              fontsize=12)
            if j == 0 and i > 0:
                ax.set_ylabel(_spec_label(param_names[i], log_scale[i]),
                              fontsize=12)
            ax.tick_params(axis='both', which='major', labelsize=8)

    fig.suptitle('MCMC parameter posterior distributions', fontsize=16, y=0.95)
    return _finish(fig, axes, out_file, show, True)


def plot_mcmc_traces(chain, log_prob_chain, param_names, log_scale=None,
                     max_walkers=10, out_file='trace_plot.png', show=False):
    """Styled trace plot of the chain, one panel per parameter.

    Args:
        chain: Array of shape ``(n_steps, n_walkers, n_params)``.
        log_prob_chain: Array of shape ``(n_steps, n_walkers)``.
        param_names: Parameter names matching the last chain axis.
        log_scale: Per-parameter log10 flags, for axis labels.
        max_walkers: Cap on how many walkers to draw, to keep it readable.
        out_file: Output filename.
        show: If True, display the figure.

    Returns:
        Path to the saved figure.
    """
    chain = np.asarray(chain)
    log_prob_chain = np.asarray(log_prob_chain)
    if chain.ndim != 3:
        raise ValueError(
            f"chain must have shape (steps, walkers, params), got {chain.shape}"
        )
    n_steps, n_walkers, n_params = chain.shape
    if log_scale is None:
        specs = GeneralModelParams.specs()
        log_scale = [specs[n].log_scale if n in specs else False
                     for n in param_names]

    shown = min(n_walkers, max_walkers)
    colors = plt.cm.tab10(np.linspace(0, 1, max(shown, 1)))

    fig, axes = plt.subplots(n_params + 1, 1,
                             figsize=(12, 3 * (n_params + 1)), sharex=True,
                             squeeze=False)
    axes = [row[0] for row in axes]

    for walker in range(shown):
        axes[0].plot(log_prob_chain[:, walker], color=colors[walker],
                     alpha=0.7, linewidth=1, label=f'Chain {walker}')
    axes[0].set_ylabel('Log probability', fontsize=12)
    axes[0].set_title('Log probability traces', fontsize=13)
    axes[0].grid(True, alpha=0.3)
    if shown <= 10:
        axes[0].legend(bbox_to_anchor=(1.01, 1), loc='upper left', fontsize=8)

    for index in range(n_params):
        ax = axes[index + 1]
        for walker in range(shown):
            ax.plot(chain[:, walker, index], color=colors[walker], alpha=0.7,
                    linewidth=1)
        ax.set_ylabel(_spec_label(param_names[index], log_scale[index]),
                      fontsize=12)
        ax.set_title(f'{param_names[index]} trace', fontsize=13)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel('MCMC step', fontsize=12)
    fig.suptitle('MCMC chain traces', fontsize=16, y=0.995)
    if shown < n_walkers:
        fig.text(0.5, 0.005, f'Showing {shown} of {n_walkers} walkers',
                 ha='center', fontsize=9, color='0.4')
    return _finish(fig, axes, out_file, show, True)


def _infer_walkers_from_flat_chain(samples, log_probs_flat, min_steps=10,
                                   max_walkers=200):
    """Guess (n_walkers, n_steps) for a flattened legacy text chain.

    Only reachable from `load_legacy_text_results`.  The guess is a factorization
    of the sample count and can be wrong; new runs save HDF5, which records the
    structure instead.
    """
    total, ndim = samples.shape
    if log_probs_flat.ndim != 1 or log_probs_flat.shape[0] != total:
        return 1, total
    candidates = [(w, total // w) for w in range(1, min(max_walkers, total) + 1)
                  if total % w == 0 and w >= max(2, 2 * ndim)
                  and total // w >= min_steps]
    return max(candidates, key=lambda pair: pair[0]) if candidates else (1, total)


def load_legacy_text_results(output_dir):
    """Read a pre-HDF5 ``mcmc_output/`` directory of ``.txt`` files.

    Kept only so existing result directories remain readable.  The walker
    structure is *inferred*, because the text format did not record it — prefer
    `card.inference.load_results` for anything newly generated.

    Args:
        output_dir: Directory holding samples.txt, log_probs.txt, param_names.txt.

    Returns:
        A results dict shaped like `card.inference.load_results` output.
    """
    import os

    samples = np.loadtxt(os.path.join(output_dir, 'samples.txt'))
    per_chain_path = os.path.join(output_dir, 'log_probs_per_chain.txt')
    log_probs = np.loadtxt(per_chain_path if os.path.exists(per_chain_path)
                           else os.path.join(output_dir, 'log_probs.txt'))
    with open(os.path.join(output_dir, 'param_names.txt')) as handle:
        param_names = [line.strip() for line in handle if line.strip()]

    if log_probs.ndim == 1:
        n_walkers, n_steps = _infer_walkers_from_flat_chain(samples, log_probs)
        log_prob_chain = log_probs.reshape(n_steps, n_walkers)
    else:
        n_steps, n_walkers = log_probs.shape
        log_prob_chain = log_probs

    return {
        'samples': samples,
        'log_probs': log_probs.reshape(-1),
        'chain': samples.reshape(n_steps, n_walkers, samples.shape[1]),
        'log_prob_chain': log_prob_chain,
        'param_names': param_names,
        'n_walkers': n_walkers,
        'n_steps': n_steps,
    }
