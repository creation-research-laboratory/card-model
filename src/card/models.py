"""
Decay models: the numerical core of CARD.

Solves radiometric dating problems in both directions for constant and
time-varying decay rates.  `DecayModel` is the interface; a new model only has
to supply `lambda_func` (and, if lambda is discontinuous, `breakpoints`) to get
working `forward_age` and `inverse_age` for free.

TIME CONVENTIONS — the name of a quantity tells you which one it uses (see
chronology.py for the full rule):

    DATE — years after Day 1 of Creation.  Model parameters (t_c, t_F, t_F2)
           and lambda(t) are DATEs.
    AGE  — years before present (YBP).  Everything passed to or returned by
           forward_age/inverse_age is an AGE.

ERROR CONTRACT — uniform across every model:

  * Invalid input raises `ValueError`.  No NaN sentinels, no silent clamping,
    no returning a plausible number for nonsense input.
  * Ages must be finite and >= 0, and no greater than `present_time` (a larger
    age would place formation before Day 1 of Creation).
  * `inverse_age` additionally rejects secular ages above `max_secular_age()`,
    which no true age in the domain can produce.
  * Model parameters are validated once, at construction.

DEPENDENCIES — this module imports the standard library and nothing else, and
`tests/test_package_structure.py` enforces that.  Every quantity here is a
scalar: numpy was only ever used as a slower spelling of `math.exp`,
`math.expm1` and `math.isfinite`, and scipy only for a bracketed root solve
(now `card._solvers.brentq`, a port that returns bit-identical results).
Dropping both is what lets the numerical core run under Pyodide without a
16 MB wheel download, and costs nothing: numpy scalars still pass the
`numbers.Real` checks, because numpy registers its scalar types with that ABC.

The one exception is the `quad` fallback in `DecayModel.compute_integral`,
which imports scipy inside the method.  It is only reachable by a subclass
that supplies no closed form, and `GeneralModel`/`ConstantDecayModel` both
override it.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, fields
from numbers import Real
from typing import Any, Dict, Sequence, Tuple
import math
import warnings

from ._solvers import brentq
from .constants import (
    AGE_OF_EARTH,
    FLOOD_START_DATE,
    LAMBDA_BG,
    MAX_UNREMARKED_FLOOD_DURATION,
    SOLVER_TOLERANCE,
)
from .parameters import (
    SPEC_KEY,
    ParamSpec,
    parameter_defaults,
    parameter_names,
    parameter_specs,
)

__all__ = [
    "ConstantDecayModel",
    "DecayModel",
    "GeneralModel",
    "GeneralModelParams",
]


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
        t_ref: DATE at which the exponential equals 1
        a: Lower limit (DATE)
        b: Upper limit (DATE)

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
        scale = -math.expm1(-decay) / k
    return math.exp(-k * (a - t_ref)) * scale


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

    All of this is checked once, in __post_init__, so a constructed instance is
    always valid.
    """
    lambda_c: float = field(metadata={SPEC_KEY: ParamSpec(
        symbol=r"\lambda_c", unit="", log_scale=True,
        description="Decay rate during the Creation week, as a multiple of background.",
        default=1.0, minimum=1.0, maximum=1e9)})
    lambda_F: float = field(metadata={SPEC_KEY: ParamSpec(
        symbol=r"\lambda_F", unit="", log_scale=True,
        description="Decay rate during the Flood, as a multiple of background.",
        default=1e5, minimum=1.0, maximum=1e9)})
    lambda_bg: float = field(metadata={SPEC_KEY: ParamSpec(
        symbol=r"\lambda_{bg}", unit="", log_scale=False,
        description="Background decay rate; always normalized to 1.",
        default=1.0, minimum=1.0, maximum=1.0)})
    k_c: float = field(metadata={SPEC_KEY: ParamSpec(
        symbol="k_c", unit="1/year", log_scale=True,
        description="Post-Creation relaxation constant; larger means faster return to background.",
        default=1e-1, minimum=0.0, maximum=1.0)})
    k_F: float = field(metadata={SPEC_KEY: ParamSpec(
        symbol="k_F", unit="1/year", log_scale=True,
        description="Post-Flood relaxation constant; larger means faster return to background.",
        default=8.04e-3, minimum=0.0, maximum=1.0)})
    t_c: float = field(metadata={SPEC_KEY: ParamSpec(
        symbol="t_c", unit="years after Creation", log_scale=False, is_date=True,
        description="DATE at which the Creation week ends.",
        default=1.0, minimum=0.0, maximum=AGE_OF_EARTH)})
    t_F: float = field(metadata={SPEC_KEY: ParamSpec(
        symbol="t_F", unit="years after Creation", log_scale=False, is_date=True,
        description="DATE at which the Flood starts.",
        default=FLOOD_START_DATE, minimum=0.0, maximum=AGE_OF_EARTH)})
    t_F2: float = field(metadata={SPEC_KEY: ParamSpec(
        symbol="t_{F2}", unit="years after Creation", log_scale=False, is_date=True,
        description="DATE at which the Flood ends; equal to t_F for an instantaneous Flood.",
        default=FLOOD_START_DATE, minimum=0.0, maximum=AGE_OF_EARTH)})

    def __post_init__(self):
        if self.lambda_bg is None:
            self.lambda_bg = LAMBDA_BG

        for name in ("lambda_c", "lambda_F", "lambda_bg", "k_c", "k_F",
                     "t_c", "t_F", "t_F2"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(
                    f"{name} must be a real number, got {value!r}"
                )
            if not math.isfinite(value):
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

    # ------------------------------------------------------------ metadata
    @classmethod
    def specs(cls) -> Dict[str, ParamSpec]:
        """Per-parameter metadata: symbol, unit, bounds, scale, description."""
        return parameter_specs(cls)

    @classmethod
    def names(cls) -> Tuple[str, ...]:
        """Parameter names in declaration order."""
        return parameter_names(cls)

    @classmethod
    def defaults(cls, **overrides: float) -> "GeneralModelParams":
        """
        Build an instance from the declared defaults, with overrides applied.

        Handy for a GUI's initial state and for tests that only care about one
        or two parameters.
        """
        values = parameter_defaults(cls)
        unknown = set(overrides) - set(values)
        if unknown:
            raise ValueError(
                f"Unrecognized parameter name(s) {sorted(unknown)}; "
                f"expected any of {sorted(values)}."
            )
        values.update(overrides)
        return cls(**values)

    # --------------------------------------------------------- serialization
    def to_dict(self) -> Dict[str, float]:
        """Plain-dict form, suitable for JSON, a config file, or a GUI form."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeneralModelParams":
        """
        Build from a plain dict.

        Unlike Chronology.from_dict this rejects unknown keys, because a
        misspelled parameter name would otherwise silently fall back to a
        default and change the model.
        """
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                f"Unrecognized parameter names: {sorted(unknown)}. "
                f"Expected any of {sorted(known)}."
            )
        missing = known - set(data)
        if missing:
            raise ValueError(f"Missing parameters: {sorted(missing)}")
        return cls(**{name: float(data[name]) for name in known})


# ============================================================================
# BASE CLASS - DECAY MODEL INTERFACE
# ============================================================================

class DecayModel(ABC):
    """
    Interface shared by all radiometric decay models.

    A subclass must define `lambda_func`.  Everything else has a working
    default:

      * `breakpoints` returns the DATEs at which lambda is discontinuous.
        Override it whenever lambda is piecewise, so the fallback quadrature
        can be told where to split.
      * `compute_integral` numerically integrates lambda/lambda_bg using
        adaptive quadrature, subdivided at the breakpoints.  Override it with
        a closed form when one exists — that is strictly better, and
        GeneralModel does exactly that.
      * `forward_age` and `inverse_age` are then generic: the forward map is
        the integral, and the inverse is a bracketed solve that is guaranteed
        to converge because lambda >= 0 makes the forward map monotone.

    Subclasses should not re-implement the domain checks; call the inherited
    `forward_age`/`inverse_age`, or use `_check_age` if overriding.
    """

    #: Background rate every other rate is normalized against.
    lambda_bg: float = LAMBDA_BG

    # ---------------------------------------------------------------- shape
    @abstractmethod
    def lambda_func(self, t: float) -> float:
        """
        Decay rate at DATE `t`, normalized so background is `lambda_bg`.

        Args:
            t: DATE (years after Day 1 of Creation)

        Returns:
            Decay rate at `t`
        """

    def breakpoints(self) -> Tuple[float, ...]:
        """
        DATEs at which `lambda_func` is discontinuous.

        Returned to the quadrature fallback so it can integrate each smooth
        piece separately.  The default is "nowhere", which is correct for
        continuous models.
        """
        return ()

    # ------------------------------------------------------------ integral
    def compute_integral(self, t_f: float, t_p: float) -> float:
        """
        Integrate the normalized decay rate over [t_f, t_p].

        Computes ∫[t_f to t_p] lambda(t)/lambda_bg dt by adaptive quadrature,
        split at any breakpoints inside the interval.  Passing the breakpoints
        matters: integrating across a discontinuity without them silently
        misplaces part of the integral.

        Override with a closed form when the model has one.

        Args:
            t_f: Formation DATE
            t_p: Present DATE

        Returns:
            The integral, normalized by lambda_bg.  Negative if the limits are
            reversed, matching the usual integral sign convention.
        """
        if t_p == t_f:
            return 0.0
        if t_p < t_f:
            return -self.compute_integral(t_p, t_f)

        from scipy.integrate import quad

        interior = sorted(b for b in self.breakpoints() if t_f < b < t_p)
        value, _ = quad(
            lambda t: self.lambda_func(t) / self.lambda_bg,
            t_f, t_p,
            points=interior or None,
            limit=200,
        )
        return value

    # ------------------------------------------------------------ contract
    @staticmethod
    def _check_age(value: float, name: str) -> float:
        """Shared validation: an age must be a finite, non-negative number."""
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a real number, got {value!r}")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite, got {value!r}")
        if value < 0.0:
            raise ValueError(
                f"{name} must be >= 0, got {value!r}.  Ages count years before "
                "present, so a negative value would be in the future."
            )
        return value

    def _check_present_time(self, present_time: float) -> float:
        if isinstance(present_time, bool) or not isinstance(present_time, Real):
            raise ValueError(
                f"present_time must be a real number, got {present_time!r}"
            )
        present_time = float(present_time)
        if not math.isfinite(present_time) or present_time <= 0.0:
            raise ValueError(
                f"present_time must be a positive, finite DATE, got "
                f"{present_time!r}"
            )
        return present_time

    # ------------------------------------------------------------- forward
    def forward_age(self, true_age: float,
                    present_time: float = AGE_OF_EARTH) -> float:
        """
        Convert a true (young-earth) age to an apparent (secular) age.

        Both are AGEs — years before present.  The true age maps to a formation
        DATE ``t_f = present_time - true_age``, and the secular age is the
        integrated decay rate from formation to now::

            secular_age = ∫[t_f → present_time] lambda(t)/lambda_bg dt

        For rocks formed long after the last acceleration the rate has already
        returned to background, so the integral equals the true age and the two
        agree.  That is correct behavior, not a degenerate case.

        Args:
            true_age: AGE at which the rock formed.  Must satisfy
                0 <= true_age <= present_time.
            present_time: DATE of the present (default: AGE_OF_EARTH).

        Returns:
            Apparent secular age in years.

        Raises:
            ValueError: If `true_age` is negative, non-finite, or exceeds
                `present_time` (which would place formation before Creation).
        """
        present_time = self._check_present_time(present_time)
        true_age = self._check_age(true_age, "true_age")
        if true_age > present_time:
            raise ValueError(
                f"true_age ({true_age:.6g}) exceeds present_time "
                f"({present_time:.6g}).  Formation would be before Day 1 of "
                "Creation, outside the model domain."
            )
        if true_age == 0.0:
            return 0.0
        return self.compute_integral(present_time - true_age, present_time)

    def max_secular_age(self, present_time: float = AGE_OF_EARTH) -> float:
        """
        Largest secular age this model can produce.

        This is `forward_age(present_time)` — the apparent age of a rock formed
        on Day 1 of Creation.  Useful as an upper bound for `inverse_age`, and
        as a slider range in a UI.
        """
        present_time = self._check_present_time(present_time)
        return self.forward_age(present_time, present_time)

    # ------------------------------------------------------------- inverse
    def inverse_age(self, secular_age: float,
                    present_time: float = AGE_OF_EARTH) -> float:
        """
        Solve for the true (young-earth) age that produces a given secular age.

        Inverts `forward_age`: finds ``true_age`` in [0, present_time] with
        ``forward_age(true_age) == secular_age``.

        Because lambda >= 0, `forward_age` is continuous and non-decreasing on
        [0, present_time], with value 0 at the lower end and `max_secular_age`
        at the upper.  Once secular ages above that maximum are rejected, the
        interval is guaranteed to bracket a root, so the bisection-based solve
        always converges — no initial guess required.

        Args:
            secular_age: Apparent age in years.  Must be in
                [0, max_secular_age(present_time)].
            present_time: DATE of the present (default: AGE_OF_EARTH).

        Returns:
            True age in years, in [0, present_time].

        Raises:
            ValueError: If `secular_age` is negative, non-finite, or larger
                than any true age in the domain can produce.
        """
        present_time = self._check_present_time(present_time)
        secular_age = self._check_age(secular_age, "secular_age")
        if secular_age == 0.0:
            return 0.0

        max_secular = self.max_secular_age(present_time)
        if secular_age > max_secular:
            raise ValueError(
                f"secular_age ({secular_age:.6g}) exceeds the maximum this "
                f"model can produce ({max_secular:.6g}, for a rock formed on "
                f"Day 1 of Creation).  No true age exists in "
                f"[0, {present_time:.6g}]."
            )

        def objective(true_age: float) -> float:
            return self.forward_age(true_age, present_time) - secular_age

        return float(brentq(objective, 0.0, present_time,
                            xtol=SOLVER_TOLERANCE, rtol=1e-15, maxiter=200))


# ============================================================================
# MODEL 1: CONSTANT DECAY RATE
# ============================================================================

class ConstantDecayModel(DecayModel):
    """
    Constant decay rate — the secular baseline.

    The decay rate never changes, so the normalized integral over any interval
    is just its length and secular age equals true age.  This is the reference
    curve every accelerated model is compared against.
    """

    def __init__(self, lambda_bg: float = LAMBDA_BG):
        """
        Args:
            lambda_bg: Background decay rate (default: 1.0, normalized).

        Raises:
            ValueError: If `lambda_bg` is not positive and finite.
        """
        if isinstance(lambda_bg, bool) or not isinstance(lambda_bg, Real):
            raise ValueError(f"lambda_bg must be a real number, got {lambda_bg!r}")
        lambda_bg = float(lambda_bg)
        if not math.isfinite(lambda_bg) or lambda_bg <= 0.0:
            raise ValueError(
                f"lambda_bg must be positive and finite, got {lambda_bg!r}"
            )
        self.lambda_bg = lambda_bg

    def lambda_func(self, t: float) -> float:
        """Decay rate is constant everywhere."""
        return self.lambda_bg

    def compute_integral(self, t_f: float, t_p: float) -> float:
        """
        Closed form: ∫ lambda_bg/lambda_bg dt = (t_p - t_f).

        Normalized like every other `compute_integral`, so the result does not
        depend on the absolute value of lambda_bg.
        """
        return t_p - t_f


# ============================================================================
# MODEL 2: GENERAL PIECEWISE MODEL
# ============================================================================

class GeneralModel(DecayModel):
    """
    General piecewise decay model with Creation, Flood, and post-Flood phases.

    Four regions, in DATEs:

    1. Creation week (t <= t_c): lambda = lambda_c (constant)
    2. Post-Creation (t_c < t <= t_F):
       lambda = (lambda_c - lambda_bg)*exp(-k_c*(t - t_c)) + lambda_bg
    3. Flood (t_F < t <= t_F2): lambda = lambda_F (constant)
    4. Post-Flood (t > t_F2):
       lambda = (lambda_F - lambda_bg)*exp(-k_F*(t - t_F2)) + lambda_bg

    This is the full @eq-general-model from docs/paper/CARD_model.qmd.
    """

    def __init__(self, params: GeneralModelParams):
        """
        Args:
            params: Validated model parameters.

        Raises:
            ValueError: If `params` is not a GeneralModelParams.
        """
        if not isinstance(params, GeneralModelParams):
            raise ValueError(
                "GeneralModel requires a GeneralModelParams instance, got "
                f"{type(params).__name__}.  Build one with "
                "GeneralModelParams(...) so the parameters are validated."
            )
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
            t_F: DATE of the (instantaneous) Flood (default: FLOOD_START_DATE)
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
        """Evaluate the piecewise decay rate at DATE `t`."""
        if t <= self.t_c:
            # Region 1: Creation week
            return self.lambda_c
        elif t <= self.t_F:
            # Region 2: Post-Creation exponential relaxation
            return ((self.lambda_c - self.lambda_bg)
                    * math.exp(-self.k_c * (t - self.t_c)) + self.lambda_bg)
        elif t <= self.t_F2:
            # Region 3: Flood constant rate
            return self.lambda_F
        else:
            # Region 4: Post-Flood exponential relaxation
            return ((self.lambda_F - self.lambda_bg)
                    * math.exp(-self.k_F * (t - self.t_F2)) + self.lambda_bg)

    def breakpoints(self) -> Tuple[float, ...]:
        """DATEs where lambda jumps: the ends of the Creation week and Flood."""
        return (self.t_c, self.t_F, self.t_F2)

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
            t_f: Formation DATE
            t_p: Present DATE

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
