"""
CARD MCMC Parameter Fitting Module

This module provides Bayesian parameter fitting for the General decay model
using Markov Chain Monte Carlo (MCMC) sampling with the emcee library.

The General model has 7 free parameters:
- lambda_c: Creation decay rate multiplier
- lambda_F: Flood decay rate multiplier  
- k_c: Creation decay constant
- k_F: Flood decay constant
- t_c: Creation event time
- t_F: Flood start time
- t_F2: Flood end time

lambda_bg is fixed at 1.0 as per model normalization.

Priors are Gaussian in log-space for stability.
Likelihood is Gaussian on secular age measurements.

TIME CONVENTIONS — this class straddles both of them, so read carefully
(see chronology.py for the naming rule):

  * `data` ages are **AGEs**: years before present.
  * `t_c`, `t_F`, `t_F2` — whether sampled or pinned via `fixed_params` —
    are **DATEs**: years after Day 1 of Creation.

Passing a DATE where an AGE belongs has produced a wrong fit before, so
prefer the named chronology constants (FLOOD_AGE, ICE_AGE_END_AGE for ages;
FLOOD_START_DATE, FLOOD_END_DATE for dates) over bare numbers.

UNITS — `fixed_params` values are **linear**, while sampled parameters are
log10 (theta_to_params applies 10**theta), as are `prior_means`/`prior_sigmas`.

Example usage is:

from card.card_mcmc import CARDMCMC

# Your data: [(young_age, secular_age, uncertainty), ...]
data = [(100, 45.2, 4.5), (500, 123.1, 12.3), ...]

fitter = CARDMCMC(data)
results = fitter.run_mcmc(n_walkers=32, n_steps=1000, burn_in=200)
fitter.save_results(results)
fitter.plot_corner(results)

"""

import numpy as np
import emcee
import corner
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict, Any
import os
from .decay_solver import GeneralModel, GeneralModelParams


class CARDMCMC:
    """
    MCMC parameter fitting for the CARD General decay model.
    
    Parameters are fit in log-space for numerical stability:
    theta = [log(lambda_c), log(lambda_F), log(k_c), log(k_F), log(t_c), log(t_F), log(t_F2)]
    """
    
    def __init__(self, 
                 data: List[Tuple[float, float, float]],
                 prior_means: Dict[str, float] = None,
                 prior_sigmas: Dict[str, float] = None,
                 fixed_params: Dict[str, float] = None):
        """
        Initialize MCMC fitter.
        
        Args:
            data: List of (young_age, secular_age, uncertainty) tuples
            prior_means: Dictionary of prior means for parameters (optional)
            prior_sigmas: Dictionary of prior standard deviations (optional)
            fixed_params: Dictionary of parameters to hold fixed during sampling
        """
        self.data = data
        self.fixed_params = fixed_params or {}
        
        # Default priors (broad, log-space)
        self.prior_means = prior_means or {
            'lambda_c': 1.0,    # log-space mean
            'lambda_F': 6.0,
            'k_c': -2.0,        # ~0.01 in linear space
            'k_F': -3.0,
            't_c': 0.0,         # ~400 years
            't_F': 3.0,         # ~1000 years  
            't_F2': 3.0         # ~1000 years
        }
        
        self.prior_sigmas = prior_sigmas or {
            'lambda_c': 3.0,    # log-space sigma
            'lambda_F': 3.0,
            'k_c': 3.0,
            'k_F': 3.0,
            't_c': 3.0,
            't_F': 3.0,
            't_F2': 3.0
        }
        
        # Parameter names and order
        self.param_names = ['lambda_c', 'lambda_F', 'k_c', 'k_F', 't_c', 't_F', 't_F2']
        for name in self.fixed_params:
            if name not in self.param_names:
                raise ValueError(f"Fixed parameter '{name}' is not recognized")
        self.free_param_names = [name for name in self.param_names if name not in self.fixed_params]
        self.ndim = len(self.free_param_names)
        
    def theta_to_params(self, theta: np.ndarray) -> GeneralModelParams:
        """
        Convert parameter vector theta to GeneralModelParams.
        
        Args:
            theta: Parameter vector [log(lambda_c), log(lambda_F), log(k_c), log(k_F), log(t_c), log(t_F), log(t_F2)]
            
        Returns:
            GeneralModelParams object
        """
        params = {}
        theta_index = 0
        for name in self.param_names:
            if name in self.fixed_params:
                params[name] = self.fixed_params[name]
            else:
                params[name] = np.power(10., theta[theta_index])
                theta_index += 1

        return GeneralModelParams(
            lambda_c=params['lambda_c'],
            lambda_F=params['lambda_F'],
            k_c=params['k_c'],
            k_F=params['k_F'],
            t_c=params['t_c'],
            t_F=params['t_F'],
            t_F2=params['t_F2'],
            lambda_bg=1.0  # Fixed
        )
    
    def log_prior(self, theta: np.ndarray) -> float:
        """
        Log prior probability for parameter vector.
        
        Uses Gaussian priors in log-space.
        
        Args:
            theta: Parameter vector
            
        Returns:
            Log prior probability
        """
        if len(theta) != self.ndim:
            return -np.inf
            
        log_prior = 0.0
        for i, param_name in enumerate(self.free_param_names):
            mean = self.prior_means[param_name]
            sigma = self.prior_sigmas[param_name]
            log_prior += -0.5 * ((theta[i] - mean) / sigma)**2
            
        return log_prior
    
    def log_likelihood(self, theta: np.ndarray) -> float:
        """
        Log likelihood for parameter vector given data.
        
        Args:
            theta: Parameter vector
            
        Returns:
            Log likelihood
        """
        try:
            params = self.theta_to_params(theta)
            model = GeneralModel(params)

            log_like = 0.0
            for young_age, secular_age_obs, uncertainty in self.data:
                secular_age_pred = model.forward_age(young_age)
                residual = (secular_age_obs - secular_age_pred) / uncertainty
                log_like += -0.5 * residual**2

            return log_like

        except ValueError:
            # GeneralModelParams validation and forward_age's domain check both
            # raise ValueError for parameter vectors outside the model's
            # support (lambda < 1, negative k, mis-ordered dates, ages before
            # Creation).  Rejecting them here is what imposes those bounds on
            # the sampler.  Deliberately narrow: any other exception is a bug
            # and should surface rather than be silently turned into -inf.
            return -np.inf
    
    def log_posterior(self, theta: np.ndarray) -> float:
        """
        Log posterior probability.
        
        Args:
            theta: Parameter vector
            
        Returns:
            Log posterior
        """
        lp = self.log_prior(theta)
        if not np.isfinite(lp):
            return -np.inf
            
        ll = self.log_likelihood(theta)
        if not np.isfinite(ll):
            return -np.inf
            
        return lp + ll
    
    def run_mcmc(
            self, 
            n_walkers: int = 32,
            n_steps: int = 1000,
            burn_in: int = 200,
            initial_guess: np.ndarray = None,
            a: float = 2.0,
            init_spread: float = 1e-4,
            output_dir: str = 'mcmc_test') -> Dict[str, Any]:
        """
        Run MCMC sampling.
        
        Args:
            n_walkers: Number of walkers (≥ 2*ndim recommended)
            n_steps: Total number of steps per walker
            burn_in: Number of initial steps to discard
            initial_guess: Initial parameter vector (optional)
            
        Returns:
            Dictionary with results
        """
        if n_walkers < 2 * self.ndim:
            print(f"Warning: n_walkers ({n_walkers}) < 2*ndim ({2*self.ndim}). Consider increasing.")
            
        # Initialize walkers
        if initial_guess is None:
            initial_guess = np.array([self.prior_means[name] for name in self.free_param_names])
        elif len(initial_guess) != self.ndim:
            raise ValueError(f"Initial guess must have length {self.ndim}")
            
        # Add small random perturbation
        pos = initial_guess + init_spread * np.random.randn(n_walkers, self.ndim)
        
        # Set up sampler
        sampler = emcee.EnsembleSampler(n_walkers, self.ndim, self.log_posterior, a=a)
        
        print(f"Running MCMC with {n_walkers} walkers for {n_steps} steps...")
        
        # Run burn-in
        if burn_in > 0:
            print(f"Burn-in phase: {burn_in} steps")
            pos, _, _ = sampler.run_mcmc(pos, burn_in, progress=True)
            sampler.reset()
            
        # Run production
        print(f"Production phase: {n_steps} steps")
        sampler.run_mcmc(pos, n_steps, progress=True)
        
        # Extract results
        chain = sampler.get_chain()  # Shape: (n_steps, n_walkers, ndim)
        samples = sampler.get_chain(flat=True)  # Shape: (n_walkers*n_steps, ndim)
        log_probs = sampler.get_log_prob(flat=True)
        
        results = {
            'chain': chain,
            'samples': samples,
            'log_probs': log_probs,
            'acceptance_fraction': np.mean(sampler.acceptance_fraction),
            'n_walkers': n_walkers,
            'n_steps': n_steps,
            'burn_in': burn_in,
            'param_names': self.free_param_names
        }
        
        return results
    
    def save_results(self, results: Dict[str, Any], output_dir: str = 'mcmc_output'):
        """
        Save MCMC results to files.
        
        Args:
            results: Results dictionary from run_mcmc
            output_dir: Output directory
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Save samples
        np.savetxt(f'{output_dir}/samples.txt', results['samples'])
        
        # Save log probabilities
        np.savetxt(f'{output_dir}/log_probs.txt', results['log_probs'])
        
        # Save acceptance fraction
        with open(f'{output_dir}/acceptance.txt', 'w') as f:
            f.write(f"Mean acceptance fraction: {results['acceptance_fraction']:.3f}\n")
            
        # Save parameter names
        with open(f'{output_dir}/param_names.txt', 'w') as f:
            for name in results['param_names']:
                f.write(f"{name}\n")
                
        print(f"Results saved to {output_dir}/")
    
    def plot_corner(self, results: Dict[str, Any], output_dir: str = 'mcmc_output'):
        """
        Create and save corner plot.
        
        Args:
            results: Results dictionary from run_mcmc
            output_dir: Output directory
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Convert samples back to linear space for plotting
        samples_linear = np.copy(results['samples'])
        for i, param_name in enumerate(results['param_names']):
            if param_name.startswith(('lambda_', 'k_', 't_')):
                samples_linear[:, i] = np.power(10., samples_linear[:, i])
                
        # Update param names for linear space
        param_names_linear = []
        for name in results['param_names']:
            if name.startswith('lambda_'):
                param_names_linear.append(f'$\\lambda_{{{name[7:]}}}$')
            elif name.startswith('k_'):
                param_names_linear.append(f'$k_{{{name[2:]}}}$')
            elif name.startswith('t_'):
                param_names_linear.append(f'$t_{{{name[2:]}}}$')
            else:
                param_names_linear.append(name)
        
        # Create corner plot
        fig = corner.corner(samples_linear, labels=param_names_linear, 
                          quantiles=[0.16, 0.5, 0.84], show_titles=True)
        fig.savefig(f'{output_dir}/corner_plot.png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        print(f"Corner plot saved to {output_dir}/corner_plot.png")
    
    def plot_convergence(self, results: Dict[str, Any], output_dir: str = 'mcmc_output'):
        """
        Create convergence diagnostic plots.
        
        Args:
            results: Results dictionary from run_mcmc
            output_dir: Output directory
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Get chain history
        chain = results.get('chain', None)
        if chain is None:
            print("Chain history not available for convergence plot")
            return
            
        n_steps, n_walkers, ndim = chain.shape
        
        # Plot trace for each parameter
        fig, axes = plt.subplots(ndim, 1, figsize=(10, 2*ndim), sharex=True)
        if ndim == 1:
            axes = [axes]
            
        for i in range(ndim):
            ax = axes[i]
            for w in range(n_walkers):
                ax.plot(chain[:, w, i], alpha=0.5, linewidth=0.5)
            ax.set_ylabel(results['param_names'][i])
            
        ax.set_xlabel('Step')
        fig.savefig(f'{output_dir}/trace_plot.png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        print(f"Trace plot saved to {output_dir}/trace_plot.png")


def example_usage():
    """
    Example usage of CARD MCMC fitting.
    """
    # Synthetic data: (young_age, secular_age, uncertainty)
    # For demonstration, create some fake data
    np.random.seed(42)
    
    # True parameters (in linear space).  Rates are multiples of the
    # background rate and so must be >= 1; the t's are DATEs (years after
    # Creation) and the Flood is brief.
    true_params = GeneralModelParams(
        lambda_c=2.0,
        lambda_F=1e5,
        k_c=0.01,
        k_F=0.005,
        t_c=400,
        t_F=1500,
        t_F2=1501,
        lambda_bg=1.0
    )

    true_model = GeneralModel(true_params)

    # Generate synthetic data.  These are AGEs (years before present).
    young_ages = np.linspace(100, 6000, 20)
    data = []
    for ya in young_ages:
        true_secular = true_model.forward_age(ya)
        # Add Gaussian noise
        uncertainty = 0.1 * true_secular  # 10% relative uncertainty
        observed_secular = np.random.normal(true_secular, uncertainty)
        data.append((ya, observed_secular, uncertainty))
    
    # Set up MCMC
    fitter = CARDMCMC(data)

    # Run MCMC
    results = fitter.run_mcmc(n_walkers=32, n_steps=500, burn_in=100)
    
    # Save results
    fitter.save_results(results)
    fitter.plot_corner(results)
    
    # Print summary
    samples = results['samples']
    for i, name in enumerate(fitter.param_names):
        median = np.median(np.power(10., samples[:, i]))
        lower = np.percentile(np.power(10., samples[:, i]), 16)
        upper = np.percentile(np.power(10., samples[:, i]), 84)
        print(f"{name}: {median:.3f} +{upper-median:.3f} -{median-lower:.3f}")


if __name__ == '__main__':
    example_usage()