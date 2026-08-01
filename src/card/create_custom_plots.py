"""
Deprecated compatibility shim for `card.create_custom_plots`.

The styled MCMC figures moved into `card.plotting` on 2026-07-26 and were
rewritten to take the results dict from `card.inference` directly, so the chain
keeps its ``(step, walker)`` structure::

    from card import plot_mcmc_corner, plot_mcmc_traces, summarize_mcmc

Name changes:

    create_custom_corner_plot  -> plot_mcmc_corner
    create_custom_trace_plot   -> plot_mcmc_traces
    create_summary_statistics  -> summarize_mcmc
    load_mcmc_results          -> load_legacy_text_results  (or, for new runs,
                                  card.inference.load_results)
    infer_walkers_from_flat_chain -> gone; it existed only because the text
                                  format lost the walker count, which HDF5
                                  records.  Legacy directories still go through
                                  the same inference internally.
"""

import os
import warnings

from .plotting import (
    load_legacy_text_results,
    plot_mcmc_corner,
    plot_mcmc_traces,
    summarize_mcmc,
)

warnings.warn(
    "card.create_custom_plots is deprecated and will be removed in a future "
    "release. Use card.plotting (plot_mcmc_corner, plot_mcmc_traces, "
    "summarize_mcmc) and card.inference.load_results.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "create_custom_corner_plot",
    "create_custom_trace_plot",
    "create_summary_statistics",
    "load_mcmc_results",
]


def load_mcmc_results(output_dir: str = 'mcmc_output'):
    """Deprecated. Returns the legacy ``(samples, log_probs, param_names)`` triple."""
    results = load_legacy_text_results(output_dir)
    return results['samples'], results['log_prob_chain'], results['param_names']


def create_custom_corner_plot(samples, param_names, prior_means=None,
                              prior_sigmas=None, output_dir='mcmc_output'):
    """Deprecated alias for `card.plotting.plot_mcmc_corner`."""
    return plot_mcmc_corner(
        samples, param_names, prior_means=prior_means,
        prior_sigmas=prior_sigmas,
        out_file=os.path.join(output_dir, 'custom_corner_plot.png'),
    )


def create_custom_trace_plot(log_probs_per_chain, param_names,
                             output_dir='mcmc_output'):
    """Deprecated alias for `card.plotting.plot_mcmc_traces`."""
    results = load_legacy_text_results(output_dir)
    return plot_mcmc_traces(
        results['chain'], results['log_prob_chain'], param_names,
        out_file=os.path.join(output_dir, 'custom_trace_plot.png'),
    )


def create_summary_statistics(samples, param_names, output_dir='mcmc_output'):
    """Deprecated alias for `card.plotting.summarize_mcmc`."""
    return summarize_mcmc(
        samples, param_names,
        out_file=os.path.join(output_dir, 'summary_statistics.txt'),
    )
