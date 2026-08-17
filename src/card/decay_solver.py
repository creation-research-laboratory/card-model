"""
Deprecated compatibility shim for the old monolithic `card.decay_solver`.

The module was split on 2026-07-26 so that the numerical core no longer drags
in a plotting stack, and so each concern has an obvious home:

    card.chronology  — the Chronology config and DATE/AGE conversions
    card.constants   — numerical settings and chronology conveniences
    card.models      — DecayModel, ConstantDecayModel, GeneralModel, params
    card.plotting    — figure generation (the only matplotlib importer)

Importing this module still works and re-exports everything from its new home,
but emits a DeprecationWarning.  Import from `card` directly instead::

    from card import GeneralModel, GeneralModelParams   # preferred
    from card.decay_solver import GeneralModel          # deprecated

Note that `card.plotting` is imported eagerly here, because the old module
exposed the plotting functions.  That defeats the lazy-import benefit, which is
another reason to migrate off this shim.
"""

import warnings

from .chronology import (
    DEFAULT_CHRONOLOGY,
    Chronology,
    years_after_creation_to_years_before_present,
    years_before_present_to_years_after_creation,
)
from .constants import (
    ACCEPTABLE_ERROR,
    AGE_OF_EARTH,
    FLOOD_AGE,
    FLOOD_DURATION,
    FLOOD_END_AGE,
    FLOOD_END_DATE,
    FLOOD_START_AGE,
    FLOOD_START_DATE,
    ICE_AGE_END_AGE,
    ICE_AGE_END_DATE,
    LAMBDA_BG,
    MAX_UNREMARKED_FLOOD_DURATION,
    PRESENT_DATE,
    SOLVER_TOLERANCE,
)
from .models import (
    ConstantDecayModel,
    DecayModel,
    GeneralModel,
    GeneralModelParams,
    _decaying_exponential_integral,
)
from .plotting import plot_age_comparison, plot_general_model_parameter_sweep

warnings.warn(
    "card.decay_solver is deprecated and will be removed in a future release. "
    "Import from `card` directly (e.g. `from card import GeneralModel`), or "
    "from card.models / card.constants / card.chronology / card.plotting.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ACCEPTABLE_ERROR",
    "AGE_OF_EARTH",
    "DEFAULT_CHRONOLOGY",
    "FLOOD_AGE",
    "FLOOD_DURATION",
    "FLOOD_END_AGE",
    "FLOOD_END_DATE",
    "FLOOD_START_AGE",
    "FLOOD_START_DATE",
    "ICE_AGE_END_AGE",
    "ICE_AGE_END_DATE",
    "LAMBDA_BG",
    "MAX_UNREMARKED_FLOOD_DURATION",
    "PRESENT_DATE",
    "SOLVER_TOLERANCE",
    "Chronology",
    "ConstantDecayModel",
    "DecayModel",
    "GeneralModel",
    "GeneralModelParams",
    "plot_age_comparison",
    "plot_general_model_parameter_sweep",
    "years_after_creation_to_years_before_present",
    "years_before_present_to_years_after_creation",
]
