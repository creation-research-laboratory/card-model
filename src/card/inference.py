"""
Bayesian parameter fitting for CARD models, using emcee.

Generalized from the original `CARDMCMC`, which hardcoded the seven
GeneralModel parameters and their log10 sampling.  This version reads all of
that from the parameter spec (see parameters.py), so fitting a different model
means declaring its parameters, not editing this file.

SAMPLING SPACE — taken from each parameter's `log_scale` flag:

  * ``log_scale=True``  (lambda_c, lambda_F, k_c, k_F): sampled as
    ``10**theta``.  Priors, initial guesses and returned samples for these are
    in **log10 units**.
  * ``log_scale=False`` (t_c, t_F, t_F2): sampled directly.  Priors and samples
    are in **linear units**.

The times used to be sampled in log10 as well.  Linear is the right choice for
a quantity that is naturally order-1-to-1e4 and may legitimately be zero, and
it costs nothing here: the main driver pins all three times, so its posterior
is unchanged.

TIME CONVENTIONS — this module straddles both (see chronology.py):

  * `data` ages are **AGEs** (years before present).
  * `t_c`, `t_F`, `t_F2` are **DATEs** (years after Day 1 of Creation).

UNITS — `fixed_params` values are always **linear**, regardless of the
parameter's sampling space.  They are model values, not sampler coordinates.

Example::

    from card import MCMCFitter, FLOOD_AGE, ICE_AGE_END_AGE, FLOOD_START_DATE

    data = [(FLOOD_AGE, 540e6, 1e7), (ICE_AGE_END_AGE, 11_500.0, 30.0)]
    fitter = MCMCFitter(data, fixed_params={
        'lambda_c': 1.0, 'k_c': 0.0, 't_c': 1.0,
        't_F': FLOOD_START_DATE, 't_F2': FLOOD_START_DATE,
    })
    results = fitter.run_mcmc(n_walkers=32, n_steps=5000, burn_in=1000)
    fitter.save_results(results, 'mcmc_output/chain.h5')
"""

import json
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .constants import AGE_OF_EARTH
from .models import GeneralModel, GeneralModelParams
from .parameters import parameter_specs, split_fixed_and_free

__all__ = ["MCMCFitter", "load_results"]

#: Default prior width, in whatever space the parameter is sampled in.
DEFAULT_PRIOR_SIGMA = 3.0


class MCMCFitter:
    """
    Fit model parameters to matched age constraints with emcee.

    Which parameters exist, whether each is sampled in log10, and their default
    priors all come from the parameter class's spec.
    """

    def __init__(self,
                 data: Sequence[Tuple[float, float, float]],
                 params_class: type = GeneralModelParams,
                 model_class: type = GeneralModel,
                 prior_means: Mapping[str, float] = None,
                 prior_sigmas: Mapping[str, float] = None,
                 fixed_params: Mapping[str, float] = None,
                 present_time: float = AGE_OF_EARTH):
        """
        Args:
            data: ``(young_age, secular_age, uncertainty)`` triples.  The young
                age is an AGE — years before present.
            params_class: Parameter dataclass carrying ParamSpec metadata.
            model_class: Model built from those parameters.
            prior_means: Gaussian prior centers, in each parameter's sampling
                space.  Defaults come from the spec.
            prior_sigmas: Gaussian prior widths, same spaces.
            fixed_params: Parameters to pin, in **linear** units.
            present_time: DATE of the present — numerically the age of the
                Earth.  Pass a `Chronology`'s `present_date` when fitting under
                a non-default chronology, or the forward ages would be computed
                against the default one while the data ages came from yours.

        Raises:
            ValueError: If `data` is empty or malformed, or if `fixed_params`
                or the priors name unknown parameters.
        """
        self.data = self._validate_data(data)
        self.present_time = float(present_time)
        self.params_class = params_class
        self.model_class = model_class
        self.specs = parameter_specs(params_class)

        self.fixed_params = dict(fixed_params or {})
        # Parameters pinned by definition (lambda_bg) are always fixed.
        for name, spec in self.specs.items():
            if not spec.is_fittable and name not in self.fixed_params:
                self.fixed_params[name] = spec.default

        self.free_param_names, _ = split_fixed_and_free(params_class,
                                                        self.fixed_params)
        self.param_names = tuple(self.specs)
        self.ndim = len(self.free_param_names)
        if self.ndim == 0:
            raise ValueError(
                "Every parameter is fixed; there is nothing to sample."
            )

        self.prior_means = self._resolve_priors(prior_means, "prior_means")
        self.prior_sigmas = self._resolve_priors(prior_sigmas, "prior_sigmas")

    # ------------------------------------------------------------- setup
    @staticmethod
    def _validate_data(data) -> List[Tuple[float, float, float]]:
        if data is None or len(data) == 0:
            raise ValueError("data must contain at least one age constraint")
        cleaned = []
        for i, row in enumerate(data):
            if len(row) != 3:
                raise ValueError(
                    f"data[{i}] must be (young_age, secular_age, uncertainty), "
                    f"got {row!r}"
                )
            young_age, secular_age, sigma = (float(v) for v in row)
            if sigma <= 0:
                raise ValueError(
                    f"data[{i}] has uncertainty {sigma!r}; it must be positive."
                )
            if young_age < 0 or secular_age < 0:
                raise ValueError(
                    f"data[{i}] has a negative age: {row!r}.  Ages count years "
                    "before present."
                )
            cleaned.append((young_age, secular_age, sigma))
        return cleaned

    def _resolve_priors(self, supplied: Mapping[str, float],
                        label: str) -> Dict[str, float]:
        """Fill in spec-derived defaults, and reject unknown names."""
        supplied = dict(supplied or {})
        unknown = set(supplied) - set(self.specs)
        if unknown:
            raise ValueError(
                f"{label} names unknown parameter(s) {sorted(unknown)}; "
                f"expected any of {sorted(self.specs)}."
            )
        resolved = {}
        for name in self.free_param_names:
            spec = self.specs[name]
            if name in supplied:
                resolved[name] = float(supplied[name])
            elif label == "prior_means":
                resolved[name] = (np.log10(max(spec.default, 1e-12))
                                  if spec.log_scale else spec.default)
            else:
                resolved[name] = DEFAULT_PRIOR_SIGMA
        return resolved

    # -------------------------------------------------------- conversion
    def theta_to_params(self, theta: np.ndarray):
        """
        Build a parameter object from a sampler coordinate.

        Free parameters are read from `theta`, undoing the log10 transform for
        those the spec marks `log_scale`; fixed parameters are inserted as-is.
        """
        values = {}
        theta_index = 0
        for name in self.param_names:
            if name in self.fixed_params:
                values[name] = self.fixed_params[name]
            else:
                raw = theta[theta_index]
                values[name] = (10.0 ** raw if self.specs[name].log_scale
                                else raw)
                theta_index += 1
        return self.params_class(**values)

    def params_to_theta(self, params) -> np.ndarray:
        """Inverse of `theta_to_params` for the free parameters."""
        out = []
        for name in self.free_param_names:
            value = getattr(params, name)
            out.append(np.log10(value) if self.specs[name].log_scale else value)
        return np.asarray(out, dtype=float)

    # --------------------------------------------------------- posterior
    def log_prior(self, theta: np.ndarray) -> float:
        """Gaussian priors, each in its parameter's sampling space."""
        if len(theta) != self.ndim:
            return -np.inf
        total = 0.0
        for i, name in enumerate(self.free_param_names):
            z = (theta[i] - self.prior_means[name]) / self.prior_sigmas[name]
            total += -0.5 * z * z
        return total

    def log_likelihood(self, theta: np.ndarray) -> float:
        """Gaussian likelihood on the secular ages."""
        try:
            model = self.model_class(self.theta_to_params(theta))
            total = 0.0
            for young_age, secular_obs, sigma in self.data:
                predicted = model.forward_age(young_age, self.present_time)
                residual = (secular_obs - predicted) / sigma
                total += -0.5 * residual * residual
            return total
        except ValueError:
            # Parameter validation and forward_age's domain check both raise
            # ValueError outside the model's support (lambda < 1, negative k,
            # mis-ordered dates, ages before Creation).  Rejecting here is what
            # imposes those bounds on the sampler.  Deliberately narrow: any
            # other exception is a bug and should surface.
            return -np.inf

    def log_posterior(self, theta: np.ndarray) -> float:
        lp = self.log_prior(theta)
        if not np.isfinite(lp):
            return -np.inf
        ll = self.log_likelihood(theta)
        if not np.isfinite(ll):
            return -np.inf
        return lp + ll

    # ------------------------------------------------------------- run
    def initial_positions(self, n_walkers: int,
                          initial_guess: Sequence[float] = None,
                          init_spread: float = 1e-4) -> np.ndarray:
        """Starting walker positions, jittered around the prior means."""
        if initial_guess is None:
            center = np.array([self.prior_means[n]
                               for n in self.free_param_names])
        else:
            center = np.asarray(initial_guess, dtype=float)
            if center.shape != (self.ndim,):
                raise ValueError(
                    f"initial_guess must have length {self.ndim}, got "
                    f"{center.shape}"
                )
        return center + init_spread * np.random.randn(n_walkers, self.ndim)

    def run_mcmc(self,
                 n_walkers: int = 32,
                 n_steps: int = 1000,
                 burn_in: int = 200,
                 initial_guess: Sequence[float] = None,
                 a: float = 2.0,
                 init_spread: float = 1e-4,
                 progress: bool = True,
                 backend_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Sample the posterior.

        Args:
            n_walkers: Number of walkers; at least 2*ndim is recommended.
            n_steps: Production steps per walker.
            burn_in: Steps to discard before production.
            initial_guess: Optional starting point in sampling space.
            a: emcee stretch-move scale.
            init_spread: Jitter applied to the starting point.
            progress: Show emcee's progress bar.
            backend_path: Optional HDF5 file for emcee to stream the chain
                into, making a long run resumable and inspectable mid-flight.

        Returns:
            Results dict.  `chain` and `log_prob_chain` keep their
            ``(step, walker)`` structure so nothing downstream has to guess it.

        Raises:
            ValueError: If `n_walkers` is too small for the sampler to move.
        """
        import emcee

        if n_walkers < 2 * self.ndim:
            raise ValueError(
                f"n_walkers ({n_walkers}) must be at least 2*ndim "
                f"({2 * self.ndim}); the stretch move cannot explore a space "
                "with fewer walkers than that."
            )

        backend = None
        if backend_path:
            os.makedirs(os.path.dirname(backend_path) or ".", exist_ok=True)
            backend = emcee.backends.HDFBackend(backend_path)
            backend.reset(n_walkers, self.ndim)

        # emcee deprecated the bare `a=` argument in favour of an explicit
        # move; StretchMove(a=a) is the same sampler it used to build.
        sampler = emcee.EnsembleSampler(
            n_walkers, self.ndim, self.log_posterior,
            moves=emcee.moves.StretchMove(a=a), backend=backend,
        )
        pos = self.initial_positions(n_walkers, initial_guess, init_spread)

        if burn_in > 0:
            state = sampler.run_mcmc(pos, burn_in, progress=progress)
            sampler.reset()
            pos = state
        sampler.run_mcmc(pos, n_steps, progress=progress)

        try:
            autocorr = sampler.get_autocorr_time(quiet=True)
        except Exception:  # pragma: no cover - emcee version differences
            autocorr = np.full(self.ndim, np.nan)

        return {
            'chain': sampler.get_chain(),                  # (steps, walkers, ndim)
            'log_prob_chain': sampler.get_log_prob(),      # (steps, walkers)
            'samples': sampler.get_chain(flat=True),
            'log_probs': sampler.get_log_prob(flat=True),
            'acceptance_fraction': float(np.mean(sampler.acceptance_fraction)),
            'autocorr_time': np.asarray(autocorr, dtype=float),
            'n_walkers': n_walkers,
            'n_steps': n_steps,
            'burn_in': burn_in,
            'present_time': self.present_time,
            'param_names': list(self.free_param_names),
            'log_scale': [self.specs[n].log_scale
                          for n in self.free_param_names],
            'fixed_params': dict(self.fixed_params),
            'prior_means': dict(self.prior_means),
            'prior_sigmas': dict(self.prior_sigmas),
        }

    # ------------------------------------------------------------- io
    def save_results(self, results: Dict[str, Any], path: str) -> str:
        """
        Write results to a single self-describing HDF5 file.

        Replaces the old directory of loose ``.txt`` files, which flattened the
        chain and so lost the walker structure — `create_custom_plots` then had
        to *guess* the walker count back with a helper that factorized the
        sample total.  Nothing has to guess now.

        Args:
            results: Dict from `run_mcmc`.
            path: Destination ``.h5`` file.

        Returns:
            The path written.
        """
        return save_results(results, path)


def save_results(results: Dict[str, Any], path: str) -> str:
    """Write an MCMC results dict to HDF5.  See `MCMCFitter.save_results`."""
    import h5py

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with h5py.File(path, 'w') as handle:
        for key in ('chain', 'log_prob_chain', 'samples', 'log_probs',
                    'autocorr_time'):
            if key in results:
                handle.create_dataset(key, data=np.asarray(results[key]),
                                      compression='gzip')
        handle.attrs['param_names'] = json.dumps(results['param_names'])
        handle.attrs['log_scale'] = json.dumps(
            [bool(b) for b in results.get('log_scale', [])])
        for key in ('acceptance_fraction', 'n_walkers', 'n_steps', 'burn_in',
                    'present_time'):
            if key in results:
                handle.attrs[key] = results[key]
        for key in ('fixed_params', 'prior_means', 'prior_sigmas'):
            if key in results:
                handle.attrs[key] = json.dumps(
                    {k: float(v) for k, v in results[key].items()})
    return path


def load_results(path: str) -> Dict[str, Any]:
    """
    Read results written by `save_results`.

    Args:
        path: Path to an ``.h5`` file.

    Returns:
        The results dict, with the chain's ``(step, walker)`` structure intact.

    Raises:
        FileNotFoundError: If `path` does not exist.
    """
    import h5py

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No MCMC results at {path!r}.  Runs are saved with "
            "MCMCFitter.save_results(results, path)."
        )

    out: Dict[str, Any] = {}
    with h5py.File(path, 'r') as handle:
        for key in handle:
            out[key] = handle[key][()]
        for key, value in handle.attrs.items():
            if key in ('param_names', 'log_scale', 'fixed_params',
                       'prior_means', 'prior_sigmas'):
                out[key] = json.loads(value)
            else:
                out[key] = value
    return out
