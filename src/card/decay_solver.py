"""
CARD (Calibrating Accelerated Radiometric Decay) Age Solver Module

Solves radiometric dating problems in both directions (forward and inverse)
for constant and variable decay rates. Supports two model complexities:
1. Constant decay rate (baseline radiometric dating)
2. General piecewise model with Creation, Flood, and post-Flood phases

The flood-only accelerated decay model is available as a limit of the
general model via the GeneralModel.flood_only() factory (no Creation-week
acceleration, instantaneous Flood).

TIME CONVENTIONS — the name of a quantity tells you which one it uses
(see chronology.py for the full rule):

    DATE — years after Day 1 of Creation.  Model parameters (t_c, t_F, t_F2)
           and lambda(t) are DATEs, because lambda is defined on the forward
           Creation timeline.
    AGE  — years before present (YBP).  Everything passed to or returned by
           forward_age/inverse_age is an AGE.

Chronology values (when the Flood was, how old the Earth is) are modeling
assumptions rather than constants; see the Chronology config class.

Unit tests live in tests/ and run with pytest.
"""

import warnings

import numpy as np
from scipy.optimize import brentq
from dataclasses import dataclass
from typing import Callable, Tuple, Optional

from .chronology import DEFAULT_CHRONOLOGY, Chronology

# Longest Flood duration (years) that passes without comment.  The Flood is
# modeled as brief relative to the post-Flood relaxation; a longer t_F2 - t_F
# is legal but likely a units or convention slip, so it is warned about.
MAX_UNREMARKED_FLOOD_DURATION = 2.0


# ============================================================================
# DEFAULT CHRONOLOGY
#
# Naming rule (see chronology.py): a quantity named *_DATE counts years AFTER
# Day 1 of Creation; a quantity named *_AGE counts years BEFORE PRESENT (YBP).
# The two run in opposite directions.
#
# These are conveniences bound to DEFAULT_CHRONOLOGY.  They are modeling
# assumptions rather than physical constants, so anything configurable should
# be passed as a Chronology instead of read from here.
# ============================================================================

AGE_OF_EARTH = DEFAULT_CHRONOLOGY.age_of_earth          # AGE of Day 1 of Creation
PRESENT_DATE = DEFAULT_CHRONOLOGY.present_date          # DATE of the present

FLOOD_START_DATE = DEFAULT_CHRONOLOGY.flood_start_date  # DATE the Flood begins
FLOOD_END_DATE = DEFAULT_CHRONOLOGY.flood_end_date      # DATE the Flood ends
FLOOD_START_AGE = DEFAULT_CHRONOLOGY.flood_start_age    # AGE the Flood begins
FLOOD_AGE = FLOOD_START_AGE                             # alias: AGE of the Flood

ICE_AGE_END_DATE = DEFAULT_CHRONOLOGY.ice_age_end_date  # DATE the Ice Age ends
ICE_AGE_END_AGE = DEFAULT_CHRONOLOGY.ice_age_end_age    # AGE the Ice Age ends

# Normalized background decay rate.  All other rates are relative to this, so
# it is always 1; GeneralModelParams normalizes any other value to 1.
LAMBDA_BG = 1.0

# Numerical tolerance for inverse problem solvers
SOLVER_TOLERANCE = 1e-10
ACCEPTABLE_ERROR = 5e-3  # Acceptable relative error for tests (5e-3 = 0.5%)


# ============================================================================
# EXACT SEGMENT INTEGRALS
# ============================================================================

def _decaying_exponential_integral(k: float, t_ref: float,
                                   a: float, b: float) -> float:
    """
    Exact value of ∫[a to b] exp(-k * (t - t_ref)) dt.

    Written as exp(-k*(a - t_ref)) * (-expm1(-k*(b - a))) / k so that it stays
    accurate for small k, where the naive difference of two exponentials
    loses all its significant digits to cancellation.  As k -> 0 the
    integrand tends to 1 and the result tends to (b - a); the series branch
    below covers that limit (including k == 0 exactly) without dividing by
    zero.

    Args:
        k: Decay constant (years^-1)
        t_ref: Time at which the exponential equals 1 (years after Creation)
        a: Lower limit (years after Creation)
        b: Upper limit (years after Creation)

    Returns:
        The exact integral; 0.0 if the interval is empty.
    """
    width = b - a
    if width <= 0.0:
        return 0.0
    decay = k * width
    if abs(decay) < 1e-8:
        # (-expm1(-x))/k = width * (1 - x/2 + x^2/6 - ...); truncating after
        # the linear term is exact to ~1e-17 relative for |x| < 1e-8.
        scale = width * (1.0 - 0.5 * decay)
    else:
        scale = -np.expm1(-decay) / k
    return np.exp(-k * (a - t_ref)) * scale


# ============================================================================
# PARAMETER DATACLASSES
# ============================================================================

@dataclass
class GeneralModelParams:
    """
    Parameters for the general piecewise decay model.

    Decay rates are normalized to the background rate, so every lambda is a
    multiple of lambda_bg and must be >= 1: the model describes decay that is
    *accelerated* relative to today, never slower than it.

    The k's are relaxation constants in lambda = (lambda_X - lambda_bg) *
    exp(-k_X * (t - t_X)) + lambda_bg.  The minus sign is already in the
    exponent, so k >= 0 is what makes lambda decay back toward background;
    k == 0 is the limiting case where it never relaxes.  A negative k would
    make lambda grow without bound and is rejected.

    The t's are DATEs (years after Day 1 of Creation) and must be ordered
    t_c <= t_F <= t_F2.  t_F == t_F2 is the instantaneous-Flood limit that
    GeneralModel.flood_only() uses.
    """
    lambda_c: float   # Creation week decay rate (>= 1, relative to background)
    lambda_F: float   # Flood decay rate (>= 1, relative to background)
    lambda_bg: float  # Background decay rate (normalized to 1)
    k_c: float        # Post-Creation relaxation constant (>= 0, years^-1)
    k_F: float        # Post-Flood relaxation constant (>= 0, years^-1)
    t_c: float        # DATE at which the Creation week ends
    t_F: float        # DATE at which the Flood starts
    t_F2: float       # DATE at which the Flood ends

    def __post_init__(self):
        if self.lambda_bg is None:
            self.lambda_bg = LAMBDA_BG

        for name in ("lambda_c", "lambda_F", "lambda_bg", "k_c", "k_F",
                     "t_c", "t_F", "t_F2"):
            value = getattr(self, name)
            if not np.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value!r}")

        if self.lambda_bg <= 0:
            raise ValueError(
                f"lambda_bg must be positive, got {self.lambda_bg!r}"
            )
        if self.lambda_bg != 1.0:
            # Only ratios to the background rate are physically meaningful, so
            # rescale rather than reject.  Every integral is of lambda/lambda_bg,
            # which is unchanged by this, but the stored values now read as the
            # multiples of background that they are.
            warnings.warn(
                f"lambda_bg was {self.lambda_bg!r}; decay rates are defined "
                "relative to the background rate, so lambda_c and lambda_F "
                "have been divided by it and lambda_bg set to 1.",
                stacklevel=2,
            )
            self.lambda_c = self.lambda_c / self.lambda_bg
            self.lambda_F = self.lambda_F / self.lambda_bg
            self.lambda_bg = 1.0

        for name in ("lambda_c", "lambda_F"):
            value = getattr(self, name)
            if value < 1.0:
                raise ValueError(
                    f"{name} ({value!r}) must be >= 1.  Decay rates are "
                    "normalized to the background rate, so a value below 1 "
                    "would mean decay slower than the present day, which the "
                    "model does not describe."
                )

        for name in ("k_c", "k_F"):
            value = getattr(self, name)
            if value < 0.0:
                raise ValueError(
                    f"{name} ({value!r}) must be >= 0.  The relaxation term is "
                    f"exp(-{name} * dt), so a negative value makes lambda grow "
                    "without bound instead of decaying back to background."
                )

        if self.t_c < 0.0:
            raise ValueError(
                f"t_c ({self.t_c!r}) must be >= 0; it is a DATE, counting "
                "years after Day 1 of Creation."
            )
        if self.t_F < self.t_c:
            raise ValueError(
                f"t_F ({self.t_F!r}) precedes t_c ({self.t_c!r}).  The DATEs "
                "must be ordered t_c <= t_F <= t_F2."
            )
        if self.t_F2 < self.t_F:
            raise ValueError(
                f"t_F2 ({self.t_F2!r}) precedes t_F ({self.t_F!r}); the Flood "
                "cannot end before it starts.  Use t_F2 == t_F for an "
                "instantaneous Flood."
            )
        if self.t_F2 - self.t_F > MAX_UNREMARKED_FLOOD_DURATION:
            warnings.warn(
                f"Flood duration t_F2 - t_F is "
                f"{self.t_F2 - self.t_F:g} years, longer than the "
                f"{MAX_UNREMARKED_FLOOD_DURATION:g}-year threshold.  Check "
                "that this is intended: t_F and t_F2 are DATEs in years after "
                "Creation, not ages before present, and the Flood is usually "
                "modeled as brief compared with the post-Flood relaxation.",
                stacklevel=2,
            )


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
    
    This is the full @eq-general-model from docs/paper/CARD_model.qmd.
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
                   t_F: float = FLOOD_START_DATE,
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
                 (default: FLOOD_START_DATE)
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
        Exactly integrate the decay rate over [t_f, t_p].

        Each of the four regions is constant or a decaying exponential, so the
        whole integral has a closed form.  The interval is clipped against each
        region in turn and the contributions are summed.

        This replaced an adaptive-quadrature implementation (scipy `quad` with
        no breakpoints).  Because lambda_func is discontinuous at t_c, t_F and
        t_F2, quad misplaced up to 0.8% of the integral for intervals spanning
        the Flood, and — more seriously — the resulting noise made forward_age
        non-monotone in true_age, which is impossible for a non-negative
        integrand and which broke the inverse solve.  Integrating in closed
        form removes both problems and is ~80x faster.

        Args:
            t_f: Formation time (years after Creation)
            t_p: Present time (years after Creation)

        Returns:
            Integrated decay rate, normalized by lambda_bg.  Negative if the
            limits are reversed, matching the usual integral sign convention.
        """
        if t_p == t_f:
            return 0.0
        if t_p < t_f:
            return -self.compute_integral(t_p, t_f)

        total = 0.0

        # Region 1 (t <= t_c): constant lambda_c
        hi = min(t_p, self.t_c)
        if hi > t_f:
            total += self.lambda_c * (hi - t_f)

        # Region 2 (t_c < t <= t_F): exponential relaxation toward lambda_bg
        lo, hi = max(t_f, self.t_c), min(t_p, self.t_F)
        if hi > lo:
            total += ((self.lambda_c - self.lambda_bg)
                      * _decaying_exponential_integral(self.k_c, self.t_c, lo, hi)
                      + self.lambda_bg * (hi - lo))

        # Region 3 (t_F < t <= t_F2): constant lambda_F (empty if t_F == t_F2)
        lo, hi = max(t_f, self.t_F), min(t_p, self.t_F2)
        if hi > lo:
            total += self.lambda_F * (hi - lo)

        # Region 4 (t > t_F2): exponential relaxation toward lambda_bg
        lo = max(t_f, self.t_F2)
        if t_p > lo:
            total += ((self.lambda_F - self.lambda_bg)
                      * _decaying_exponential_integral(self.k_F, self.t_F2, lo, t_p)
                      + self.lambda_bg * (t_p - lo))

        return total / self.lambda_bg
    
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

        # forward_age integrates a non-negative lambda, so it is continuous and
        # non-decreasing on [0, present_time], with forward_age(0) == 0 and
        # forward_age(present_time) == max_secular.  Having already rejected
        # secular_age > max_secular above, [0, present_time] is guaranteed to
        # bracket a root, so a bisection-based solver always converges.
        #
        # This replaced an fsolve call seeded by a hand-tuned initial guess.
        # fsolve is a multidimensional Powell solver being applied to a 1-D
        # monotone problem, and the out-of-domain penalty it needed made the
        # objective discontinuous; it failed on up to 17% of targets for
        # short, intense Flood parameters.
        def objective(t_true: float) -> float:
            return self.forward_age(t_true, present_time) - secular_age

        true_age = float(brentq(objective, 0.0, present_time,
                                xtol=SOLVER_TOLERANCE, rtol=1e-15, maxiter=200))

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

    FLOOD_SECULAR_AGE = general_model.forward_age(FLOOD_START_AGE)

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
    plt.axvline(x=FLOOD_START_AGE, color="red", linestyle="--", label="Flood event")
    plt.axhline(y=FLOOD_SECULAR_AGE, color="purple", linestyle="--", label="Flood secular age")
    plt.xlabel("Young age (years before present)")
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
    plt.axvline(x=FLOOD_START_AGE, color="red", linestyle="--", alpha=0.7, label="Flood event")
    plt.axhline(y=540e6, color="purple", linestyle="--", alpha=0.7, label="540 Myr secular age")

    plt.xlabel("Young age (years before present)")
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
    # Posterior-median flood-only model: no Creation-week acceleration
    # (lambda_c == lambda_bg), instantaneous Flood (t_F == t_F2).
    base_params = GeneralModelParams(
        lambda_c=LAMBDA_BG,
        lambda_F=10**5.7628,
        lambda_bg=LAMBDA_BG,
        k_c=1,
        k_F=10**-2.8562,
        t_c=1,
        t_F=FLOOD_START_DATE,
        t_F2=FLOOD_END_DATE,
    )

    # Define parameters to vary.  Every lambda_F here is >= 1, as the model
    # requires: rates are multiples of the background rate.
    vary_params = {
        'lambda_F': [10**5.4, 10**5.7628, 10**6.1],
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
