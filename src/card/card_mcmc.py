"""
Deprecated compatibility shim for `card.card_mcmc`.

The fitter moved to `card.inference` on 2026-07-26 and was generalized to read
its parameter list, sampling spaces and default priors from the parameter spec
(see parameters.py) instead of hardcoding the seven GeneralModel parameters.

Import `MCMCFitter` from `card` instead::

    from card import MCMCFitter          # preferred
    from card.card_mcmc import CARDMCMC  # deprecated

Two API changes the adapter below smooths over, both with a warning:

  * ``run_mcmc(output_dir=...)`` — the argument was never used; it is ignored.
  * ``save_results(results, output_dir=...)`` — results are now one
    self-describing HDF5 file rather than a directory of ``.txt`` files, so the
    directory form writes ``<output_dir>/chain.h5``.

Chain plotting moved to `card.plotting` (`plot_mcmc_corner`,
`plot_mcmc_traces`, `summarize_mcmc`), which keeps the styled versions.
"""

import os
import warnings
from typing import Any, Dict

from .inference import MCMCFitter, load_results, save_results

warnings.warn(
    "card.card_mcmc is deprecated and will be removed in a future release. "
    "Use `from card import MCMCFitter` (chain plotting now lives in "
    "card.plotting).",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["CARDMCMC", "MCMCFitter", "load_results", "save_results"]


class CARDMCMC(MCMCFitter):
    """Deprecated name for `card.inference.MCMCFitter`."""

    def run_mcmc(self, *args, output_dir: str = None, **kwargs) -> Dict[str, Any]:
        if output_dir is not None:
            warnings.warn(
                "run_mcmc(output_dir=...) never had any effect and has been "
                "removed; pass backend_path=... to stream the chain to HDF5, "
                "or save afterwards with save_results(results, path).",
                DeprecationWarning, stacklevel=2,
            )
        return super().run_mcmc(*args, **kwargs)

    def save_results(self, results: Dict[str, Any], path: str = None,
                     output_dir: str = None) -> str:
        if output_dir is not None:
            warnings.warn(
                "save_results(output_dir=...) is deprecated; results are now a "
                "single HDF5 file. Writing to "
                f"{os.path.join(output_dir, 'chain.h5')!r}.",
                DeprecationWarning, stacklevel=2,
            )
            path = os.path.join(output_dir, "chain.h5")
        if path is None:
            raise ValueError("save_results requires a destination path")
        return super().save_results(results, path)
