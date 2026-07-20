"""
CARD (Calibrating Accelerated Radiometric Decay) Age Solver Module

Solves radiometric dating problems in both directions (forward and inverse)
for constant and variable decay rates. Supports two model complexities:
1. Constant decay rate (baseline radiometric dating)
2. General piecewise model with Creation, Flood, and post-Flood phases

The flood-only accelerated decay model is available as a limit of the
general model via the GeneralModel.flood_only() factory (no Creation-week
acceleration, instantaneous Flood).

All times are in "years after Day 1 of Creation" unless otherwise noted.

Unit tests live in tests/ and run with pytest.
"""

import numpy as np
from scipy.integrate import quad
from scipy.optimize import fsolve
from dataclasses import dataclass
from typing import Callable, Tuple, Optional


# ============================================================================
# GLOBAL CONFIGURATION CONSTANTS
# ============================================================================

# Age of Earth in years after Day 1 of Creation (young-earth model)
AGE_OF_EARTH = 6056

# Flood event timing (years after Creation)
FLOOD_START = 1656  # Time of Flood start
FLOOD_END = 1656    # If FLOOD_START == FLOOD_END, instantaneous transition for flood-only model
FLOOD_AGE = AGE_OF_EARTH - FLOOD_START  # Age of Flood event in years before present (YBP)

# Ice Age end (years after Creation)
ICE_AGE_END_AGE = 3500
ICE_AGE_END_YBP = AGE_OF_EARTH - ICE_AGE_END_AGE  # Ice Age end in years before present (YBP)

# Precambrian-Cambrian boundary timing (years after Creation)
PC_CAMBRIAN_BOUNDARY = 5400

# Normalized background decay rate (all other rates are relative to this)
LAMBDA_BG = 1.0

# Numerical tolerance for inverse problem solvers
SOLVER_TOLERANCE = 1e-10
ACCEPTABLE_ERROR = 5e-3  # Acceptable relative error for tests (5e-3 = 0.5%)


# ============================================================================
# PARAMETER DATACLASSES
# ============================================================================

@dataclass
class GeneralModelParams:
    """Parameters for general piecewise decay model."""
    lambda_c: float   # Creation week decay rate
    lambda_F: float   # Flood decay rate
    lambda_bg: float  # Background decay rate (default: 1.0)
    k_c: float        # Post-Creation decay constant
    k_F: float        # Post-Flood decay constant
    t_c: float        # End of Creation week (years after Creation)
    t_F: float        # Start of Flood
    t_F2: float       # End of Flood
    
    def __post_init__(self):
        if self.lambda_bg is None:
            self.lambda_bg = LAMBDA_BG


# ============================================================================
# BASE CLASS - DECAY MODEL INTERFACE
# ============================================================================

class DecayModel:
    """Abstract base class for radiometric decay models."""
    
    def lambda_func(self, t: float) -> float:
        """
        Return normalized decay rate at time t.
        
        Args:
            t: Time in years after Day 1 of Creation
            
        Returns:
            Normalized decay rate (relative to background)
        """
        raise NotImplementedError
    
    def compute_integral(self, t_f: float, t_p: float) -> float:
        """
        Numerically integrate decay rate from t_f to t_p.
        
        Computes: ∫[t_f to t_p] λ(t')/λ_bg dt'
        
        Args:
            t_f: Formation time (years after Creation)
            t_p: Present time (years after Creation)
            
        Returns:
            Integrated decay rate
        """
        raise NotImplementedError
    
    def forward_age(self, true_age: float, present_time: float = AGE_OF_EARTH) -> float:
        """
        Convert true (young-earth) age to apparent (secular) age.

        Both ages use the "years before present" (YBP) convention:
            true_age  = present_time - t_f
            secular_age = ∫[t_f → present_time] λ(t)/λ_bg dt

        where t_f is the formation time in "years after Day 1 of Creation".
        This is distinct from "years after end of Creation week" (t_f - t_c).

        Args:
            true_age: Years before present at which the rock formed (YBP).
                      Must be in [0, present_time]; values outside this range
                      imply formation before Day 1 of Creation.
            present_time: Current time in years after Day 1 of Creation
                          (default: AGE_OF_EARTH)

        Returns:
            Apparent secular age in years (YBP convention)
        """
        raise NotImplementedError

    def inverse_age(self, secular_age: float, present_time: float = AGE_OF_EARTH) -> float:
        """
        Convert apparent (secular) age to true (young-earth) age.

        Inverts forward_age: finds true_age such that
            forward_age(true_age, present_time) == secular_age.

        Both ages use the "years before present" (YBP) convention.
        The true age returned is in [0, present_time], corresponding to
        formation times between Day 1 of Creation and the present.

        Args:
            secular_age: Apparent age in years (YBP convention). Must be >= 0
                         and <= the maximum achievable secular age for this model
                         (forward_age(present_time)).
            present_time: Current time in years after Day 1 of Creation
                          (default: AGE_OF_EARTH)

        Returns:
            True rock age in years (YBP convention), in [0, present_time]
        """
        raise NotImplementedError


# ============================================================================
# MODEL 1: CONSTANT DECAY RATE
# ============================================================================

class ConstantDecayModel(DecayModel):
    """
    Simple constant decay rate model (baseline radiometric dating).
    
    In this model, the decay rate λ is constant and equal to λ_bg.
    The radioactive decay equation has the analytical solution:
        N(t) = N_0 * exp(-λ_bg * t)
    
    The relationship between true age (t_ya) and secular age (t_sec) is:
        t_sec = t_ya  (they are identical under constant decay)
    """
    
    def __init__(self, lambda_bg: float = LAMBDA_BG):
        """
        Initialize constant decay model.
        
        Args:
            lambda_bg: Background decay rate (default: 1.0, normalized)
        """
        self.lambda_bg = lambda_bg
    
    def lambda_func(self, t: float) -> float:
        """Decay rate is constant."""
        return self.lambda_bg
    
    def compute_integral(self, t_f: float, t_p: float) -> float:
        """
        Analytical integral: ∫ λ_bg dt = λ_bg * (t_p - t_f)
        """
        return self.lambda_bg * (t_p - t_f)
    
    def forward_age(self, true_age: float, present_time: float = AGE_OF_EARTH) -> float:
        """Under constant decay, true age equals secular age."""
        if true_age < 0:
            raise ValueError("Age cannot be negative")
        return true_age
    
    def inverse_age(self, secular_age: float, present_time: float = AGE_OF_EARTH) -> float:
        """Under constant decay, secular age equals true age."""
        if secular_age < 0:
            raise ValueError("Age cannot be negative")
        return secular_age


# ============================================================================
# MODEL 2: GENERAL PIECEWISE MODEL
# ============================================================================

class GeneralModel(DecayModel):
    """
    General piecewise decay model with Creation, Flood, and post-Flood phases.
    
    Four decay rate regions:
    1. Creation week (0 < t < t_c): λ = λ_c (constant)
    2. Post-Creation (t_c < t < t_F): λ = (λ_c - λ_bg)*exp(-k_c*(t - t_c)) + λ_bg (exponential decay)
    3. Flood (t_F < t ≤ t_F2): λ = λ_F (constant)
    4. Post-Flood (t > t_F2): λ = (λ_F - λ_bg)*exp(-k_F*(t - t_F2)) + λ_bg (exponential decay)
    
    This is the full @eq-general-model from RIAG_model.qmd documentation.
    """
    
    def __init__(self, params: GeneralModelParams):
        """
        Initialize general piecewise model.
        
        Args:
            params: GeneralModelParams object with all model parameters
        """
        self.params = params
        self.lambda_bg = params.lambda_bg
        self.lambda_c = params.lambda_c
        self.lambda_F = params.lambda_F
        self.k_c = params.k_c
        self.k_F = params.k_F
        self.t_c = params.t_c
        self.t_F = params.t_F
        self.t_F2 = params.t_F2

    @classmethod
    def flood_only(cls, lambda_F: float, k_F: float,
                   t_F: float = FLOOD_START,
                   lambda_bg: float = LAMBDA_BG) -> "GeneralModel":
        """
        Flood-only limit of the general model.

        No Creation-week acceleration (lambda_c == lambda_bg, so k_c and t_c
        are irrelevant) and an instantaneous Flood (t_F == t_F2).  The decay
        rate is lambda_bg before the Flood, then decays exponentially from
        lambda_F back toward lambda_bg after it.

        Args:
            lambda_F: Peak decay rate at the Flood (normalized to background)
            k_F: Post-Flood decay constant (years^-1)
            t_F: Time of the (instantaneous) Flood in years after Creation
                 (default: FLOOD_START)
            lambda_bg: Background decay rate (default: 1.0)

        Returns:
            GeneralModel configured in the flood-only limit
        """
        params = GeneralModelParams(
            lambda_c=lambda_bg,
            lambda_F=lambda_F,
            lambda_bg=lambda_bg,
            k_c=1.0,  # irrelevant: lambda_c == lambda_bg
            k_F=k_F,
            t_c=1.0,
            t_F=t_F,
            t_F2=t_F,
        )
        return cls(params)

    def lambda_func(self, t: float) -> float:
        """
        Evaluate decay rate at given time (years after Creation).
        
        Implements piecewise function with four regions.
        """
        if t <= self.t_c:
            # Region 1: Creation week
            return self.lambda_c
        elif t <= self.t_F:
            # Region 2: Post-Creation exponential decay
            return (self.lambda_c - self.lambda_bg) * np.exp(-self.k_c * (t - self.t_c)) + self.lambda_bg
        elif t <= self.t_F2:
            # Region 3: Flood constant rate
            return self.lambda_F
        else:
            # Region 4: Post-Flood exponential decay
            return (self.lambda_F - self.lambda_bg) * np.exp(-self.k_F * (t - self.t_F2)) + self.lambda_bg
    
    def compute_integral(self, t_f: float, t_p: float) -> float:
        """
        Numerically integrate decay rate over interval [t_f, t_p].
        
        Piecewise integration: detects which regions the interval spans
        and computes each analytically, then sums results.
        
        Args:
            t_f: Formation time (years after Creation)
            t_p: Present time (years after Creation)
            
        Returns:
            Integrated decay rate
        """
        if t_f == t_p:
            return 0.0
        
        # Define integrand
        def integrand(t):
            return self.lambda_func(t) / self.lambda_bg
        
        # Use scipy.integrate.quad for accurate numerical integration
        result, error = quad(integrand, t_f, t_p, limit=100)
        return result
    
    def forward_age(self, true_age: float, present_time: float = AGE_OF_EARTH) -> float:
        """
        Convert true (young-earth) age to apparent (secular) age.

        "True age" is years before present (YBP): the time elapsed from the
        rock's formation to now.  Internally this maps to a formation time
            t_f = present_time - true_age   (years after Day 1 of Creation)
        which must lie in [0, present_time].  Values outside that range —
        i.e. true_age > present_time — would place t_f before Day 1 of
        Creation and are outside the model domain.

        Note on apparent identity for small ages: for rocks formed deep in
        the post-Flood era the decay rate has already returned to background
        (λ ≈ λ_bg), so the integral equals true_age and secular_age ≈
        true_age.  This is correct physical behavior, not a bug.

        Args:
            true_age: Years before present at which the rock formed (YBP).
                      Must satisfy 0 ≤ true_age ≤ present_time.
            present_time: Current time in years after Day 1 of Creation
                          (default: AGE_OF_EARTH).

        Returns:
            Apparent secular age in years (YBP convention).

        Raises:
            ValueError: If true_age > present_time (formation before Creation).
        """
        if true_age < 0:
            # Return NaN for invalid ages so that root-finding in inverse_age
            # can penalize this region without a hard exception.
            return np.nan
        if true_age > present_time:
            raise ValueError(
                f"true_age ({true_age:.4g}) exceeds present_time ({present_time}). "
                "Formation would be before Day 1 of Creation, outside model domain."
            )
        if true_age == 0:
            return 0.0

        t_f = present_time - true_age  # Formation time (years after Creation)
        t_p = present_time             # Present time (years after Creation)

        return self.compute_integral(t_f, t_p)
    
    def inverse_age(self, secular_age: float, present_time: float = AGE_OF_EARTH) -> float:
        """
        Solve for true (young-earth) age given apparent (secular) age.

        Inverts forward_age numerically: finds true_age in [0, present_time]
        such that forward_age(true_age, present_time) == secular_age.

        "Secular age" is the apparent age in years before present (YBP) as
        implied by an isotope ratio under constant-decay assumptions.  "True
        age" is the actual elapsed time from formation to present (YBP).

        The secular age must be achievable within the model, i.e. it must be
        ≤ forward_age(present_time) — the secular age of a rock formed on
        Day 1 of Creation.  Larger secular ages have no valid solution in the
        [0, present_time] domain and will raise ValueError.

        Args:
            secular_age: Apparent age in years (YBP convention). Must be in
                         [0, forward_age(present_time)].
            present_time: Current time in years after Day 1 of Creation
                          (default: AGE_OF_EARTH).

        Returns:
            True rock age in years (YBP convention), in [0, present_time].

        Raises:
            ValueError: If secular_age < 0, or if the solver cannot find a
                        valid solution in [0, present_time] (secular age
                        exceeds the model's maximum achievable value).
        """
        if secular_age < 0:
            raise ValueError("Secular age cannot be negative")
        if secular_age == 0:
            return 0.0

        # Maximum secular age the model can produce for a rock formed on
        # Day 1 of Creation (true_age == present_time, t_f == 0).
        max_secular = self.forward_age(present_time, present_time)
        if secular_age > max_secular:
            raise ValueError(
                f"secular_age ({secular_age:.4g}) exceeds the maximum secular age "
                f"this model can produce ({max_secular:.4g}, for a rock formed on "
                f"Day 1 of Creation).  No valid true age exists in [0, {present_time}]."
            )

        # Smart initial guess: try both constant-decay estimate and a smaller estimate
        # For models with accelerated decay, the true age is much smaller than secular age
        constant_model = ConstantDecayModel(self.lambda_bg)
        guess1 = constant_model.inverse_age(secular_age, present_time)

        # Also try a guess that assumes this behaves somewhat like flood model
        R_approx = (self.lambda_F - self.lambda_bg) / self.lambda_bg if self.lambda_F > self.lambda_bg else 1.0
        k_approx = min(self.k_c, self.k_F) if hasattr(self, 'k_c') and self.k_c > 0 else self.k_F
        guess2 = max(secular_age * k_approx / max(R_approx, 1), 1.0) if R_approx > 1 else guess1

        # Use the smaller guess as it's more likely to be in the right ballpark
        initial_guess = min(guess1, guess2) if guess2 < guess1 * 0.5 else guess1
        # Clamp to valid domain
        initial_guess = min(initial_guess, present_time)

        # Define objective function; penalise out-of-domain candidates so the
        # solver stays within [0, present_time].
        def objective(t_true_arr):
            t_true = float(t_true_arr[0]) if isinstance(t_true_arr, np.ndarray) else float(t_true_arr)
            if t_true > present_time:
                return np.array([1e10])
            result = self.forward_age(t_true, present_time)
            if np.isnan(result):
                return np.array([1e10])
            return np.array([result - secular_age])

        # Solve using scipy.optimize.fsolve
        solution = fsolve(objective, np.array([initial_guess]), xtol=SOLVER_TOLERANCE, full_output=False)
        true_age = float(solution[0])

        # Verify the solution is in the valid domain and actually converged.
        if true_age < 0 or true_age > present_time:
            raise ValueError(
                f"inverse_age solver returned true_age={true_age:.4g}, which is outside "
                f"the valid domain [0, {present_time}].  The secular_age ({secular_age:.4g}) "
                f"may be too large for this model."
            )
        recovered = self.forward_age(true_age, present_time)
        rel_error = abs(recovered - secular_age) / (secular_age + 1e-10)
        if rel_error > ACCEPTABLE_ERROR:
            raise ValueError(
                f"inverse_age solver did not converge for secular_age={secular_age:.4g}. "
                f"Best solution: true_age={true_age:.4g} gives secular_age={recovered:.4g} "
                f"(relative error {rel_error:.2e} > tolerance {ACCEPTABLE_ERROR})."
            )

        return true_age


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def years_before_present_to_years_after_creation(years_ago: float, 
                                                   age_of_earth: float = AGE_OF_EARTH) -> float:
    """
    Convert years before present (YBP) to years after Day 1 of Creation.
    
    Args:
        years_ago: Time in years before present (YBP convention)
        age_of_earth: Age of Earth in years after Creation
        
    Returns:
        Time in years after Day 1 of Creation
    """
    return age_of_earth - years_ago


def years_after_creation_to_years_before_present(years_after: float,
                                                  age_of_earth: float = AGE_OF_EARTH) -> float:
    """
    Convert years after Day 1 of Creation to years before present (YBP).
    
    Args:
        years_after: Time in years after Day 1 of Creation
        age_of_earth: Age of Earth in years after Creation
        
    Returns:
        Time in years before present (YBP)
    """
    return age_of_earth - years_after


# ============================================================================
# PLOTTING UTILITIES
# ============================================================================

def plot_age_comparison(
    age_of_earth: float = AGE_OF_EARTH,
    n_points: int = 1000,
    out_file: str = "age_comparison_plot.png",
    show: bool = False,
    lambda_F: float = 5e5,
    k_F: float = 0.5e-2,
    lambda_F_median: float = None,
    k_F_median: float = None,
):
    """Create a comparison plot of secular age vs young age for each model.

    Args:
        age_of_earth: Present-time age in years (years after Creation).
        n_points: Number of sample points between 0 and age_of_earth.
        out_file: Output filename to save the figure.
        show: If True, call plt.show().
        lambda_F: Posterior mean lambda_F for the general model.
        k_F: Posterior mean k_F for the general model.
        lambda_F_median: Posterior median lambda_F for the general model.
        k_F_median: Posterior median k_F for the general model.

    Returns:
        str: Path to saved figure.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    const_model = ConstantDecayModel(lambda_bg=LAMBDA_BG)
    general_params = GeneralModelParams(
        lambda_c=1,
        lambda_F=lambda_F,
        lambda_bg=LAMBDA_BG,
        k_c=1,
        k_F=k_F,
        t_c=1,
        t_F=1656,
        t_F2=1656,
    )
    general_model = GeneralModel(general_params)
    if lambda_F_median is not None and k_F_median is not None:
        median_params = GeneralModelParams(
            lambda_c=1,
            lambda_F=lambda_F_median,
            lambda_bg=LAMBDA_BG,
            k_c=1,
            k_F=k_F_median,
            t_c=1,
            t_F=1656,
            t_F2=1656,
        )
        median_model = GeneralModel(median_params)

    FLOOD_SECULAR_AGE = general_model.forward_age(AGE_OF_EARTH - FLOOD_START)

    x = np.linspace(0, age_of_earth, n_points)
    y_const = np.array([const_model.forward_age(t) for t in x])
    y_general = np.array([general_model.forward_age(t) for t in x])
    if lambda_F_median is not None and k_F_median is not None:
        y_general_median = np.array([median_model.forward_age(t) for t in x])

    plt.figure(figsize=(10, 6))
    plt.semilogy(x, y_const, label="Constant decay", color="blue")
    plt.semilogy(x, y_general, label="Posterior mean general", color="green")
    if lambda_F_median is not None and k_F_median is not None:
        plt.semilogy(x, y_general_median, label="Posterior median general", color="purple", linestyle="--")
    plt.axvline(x=AGE_OF_EARTH - FLOOD_START, color="red", linestyle="--", label="Flood event")
    plt.axhline(y=FLOOD_SECULAR_AGE, color="purple", linestyle="--", label="Flood secular age")
    plt.xlabel("Young-age (years since Creation)")
    plt.ylabel("Secular age (years)")
    plt.title("Secular age vs Young-age (0 to present)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(out_file, dpi=180, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()
    return out_file


def plot_general_model_parameter_sweep(
    base_params: GeneralModelParams = None,
    vary_params: dict = None,
    age_of_earth: float = AGE_OF_EARTH,
    n_points: int = 1000,
    out_file: str = "general_model_sweep_plot.png",
    show: bool = False,
):
    """Create a plot showing multiple GeneralModel calculations with varied parameters.

    Args:
        base_params: Base GeneralModelParams to use as defaults. If None, uses standard values.
        vary_params: Dict of {param_name: [list_of_values]} to vary. 
                    Valid param names: lambda_c, lambda_F, lambda_bg, k_c, k_F, t_c, t_F, t_F2
        age_of_earth: Present-time age in years (years after Creation).
        n_points: Number of sample points between 0 and age_of_earth.
        out_file: Output filename to save the figure.
        show: If True, call plt.show().

    Returns:
        str: Path to saved figure.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from itertools import product
    import matplotlib.cm as cm

    # Set default base parameters if not provided
    if base_params is None:
        base_params = GeneralModelParams(
            lambda_c=1e3,
            lambda_F=1e5,
            lambda_bg=1.0,
            k_c=1e-1,
            k_F=8.04e-3,
            t_c=1,
            t_F=1656,
            t_F2=1657
        )

    # Set default vary_params if not provided
    if vary_params is None:
        vary_params = {
            'lambda_F': [1e5, 5e5, 1e6],
            'k_F': [2e-3, 5e-3, 8e-3]
        }

    # Convert base_params to dict for easy manipulation
    base_dict = {
        'lambda_c': base_params.lambda_c,
        'lambda_F': base_params.lambda_F,
        'lambda_bg': base_params.lambda_bg,
        'k_c': base_params.k_c,
        'k_F': base_params.k_F,
        't_c': base_params.t_c,
        't_F': base_params.t_F,
        't_F2': base_params.t_F2
    }

    # Generate all parameter combinations
    param_names = list(vary_params.keys())
    param_values = list(vary_params.values())
    combinations = list(product(*param_values))

    # Create color map
    colors = cm.viridis(np.linspace(0, 1, len(combinations)))

    # Generate x values
    x = np.linspace(0, age_of_earth, n_points)

    plt.figure(figsize=(12, 8))

    const_model = ConstantDecayModel(lambda_bg=LAMBDA_BG)
    x = np.linspace(0, age_of_earth, n_points)
    y_const = np.array([const_model.forward_age(t) for t in x])
    plt.semilogy(x, y_const, label="Constant decay", color="blue")

    # Plot each parameter combination
    for i, combo in enumerate(combinations):
        # Create parameter dict for this combination
        params_dict = base_dict.copy()
        for j, param_name in enumerate(param_names):
            params_dict[param_name] = combo[j]

        # Create GeneralModelParams object
        model_params = GeneralModelParams(**params_dict)
        model = GeneralModel(model_params)

        # Compute y values
        y = np.array([model.forward_age(t) for t in x])

        # Create label showing varied parameters
        label_parts = []
        for j, param_name in enumerate(param_names):
            value = combo[j]
            if value >= 1e3:
                label_parts.append(f"{param_name}={value:.0e}")
            elif value >= 1:
                label_parts.append(f"{param_name}={value:.1f}")
            else:
                label_parts.append(f"{param_name}={value:.2e}")
        label = ", ".join(label_parts)

        plt.semilogy(x, y, color=colors[i], linewidth=2, label=label)

    # Add reference lines
    plt.axvline(x=AGE_OF_EARTH - FLOOD_START, color="red", linestyle="--", alpha=0.7, label="Flood event")
    plt.axhline(y=540e6, color="purple", linestyle="--", alpha=0.7, label="540 Myr secular age")

    plt.xlabel("Young-age (years since Creation)")
    plt.ylabel("Secular age (years)")
    plt.title("General Model Parameter Sweep: Secular age vs Young-age")
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_file, dpi=180, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()
    return out_file


if __name__ == "__main__":
    # Example usage of parameter sweep plotting
    base_params = GeneralModelParams(
        lambda_c=0,
        lambda_F=10**5.7628,
        lambda_bg=1.0,
        k_c=1,
        k_F=10**-2.8562,
        t_c=1,
        t_F=1656,
        t_F2=1656,
    )
    
    # Define parameters to vary
    vary_params = {
        'lambda_F': [10**-5.5, 10**5.7628, 10**6.1],
        'k_F': [10**-3.1, 10**-2.8562, 10**-2.6]
    }
    
    plot_general_model_parameter_sweep(
        base_params=base_params,
        vary_params=vary_params,
        out_file="general_model_sweep_plot.png",
        show=False
    )
    
    # Also run the original comparison plot
    plot_age_comparison(out_file="age_comparison_plot.png", show=False)
