"""
Package-level constants for CARD.

Two kinds of value live here, and they are not the same kind of thing:

  * **Numerical settings** (LAMBDA_BG, solver tolerances, warning thresholds)
    are genuine constants of the implementation.
  * **Chronology conveniences** (AGE_OF_EARTH, FLOOD_START_DATE, ...) are
    modeling assumptions bound to DEFAULT_CHRONOLOGY.  They are re-exported
    here for brevity, but anything configurable should take a `Chronology`
    rather than reading these — see chronology.py.

Naming rule: a quantity named ``*_DATE`` counts years AFTER Day 1 of Creation;
a quantity named ``*_AGE`` counts years BEFORE PRESENT.  The two run in
opposite directions and a matching pair sums to AGE_OF_EARTH.
"""

from .chronology import DEFAULT_CHRONOLOGY

# ---------------------------------------------------------------- chronology
AGE_OF_EARTH = DEFAULT_CHRONOLOGY.age_of_earth          # AGE of Day 1 of Creation
PRESENT_DATE = DEFAULT_CHRONOLOGY.present_date          # DATE of the present

FLOOD_START_DATE = DEFAULT_CHRONOLOGY.flood_start_date  # DATE the Flood begins
FLOOD_END_DATE = DEFAULT_CHRONOLOGY.flood_end_date      # DATE the Flood ends
FLOOD_START_AGE = DEFAULT_CHRONOLOGY.flood_start_age    # AGE the Flood begins
FLOOD_AGE = FLOOD_START_AGE                             # alias: AGE of the Flood

ICE_AGE_END_DATE = DEFAULT_CHRONOLOGY.ice_age_end_date  # DATE the Ice Age ends
ICE_AGE_END_AGE = DEFAULT_CHRONOLOGY.ice_age_end_age    # AGE the Ice Age ends

# ------------------------------------------------------------------ numerics
# Normalized background decay rate.  All other rates are multiples of this, so
# it is always 1; GeneralModelParams normalizes any other value to 1.
LAMBDA_BG = 1.0

# Absolute tolerance (in years) for the bracketed inverse-age solve.
SOLVER_TOLERANCE = 1e-10

# Relative error still considered acceptable when verifying a solved age.
ACCEPTABLE_ERROR = 5e-3

# Longest Flood duration (years) that passes without comment.  The Flood is
# modeled as brief relative to the post-Flood relaxation; a longer t_F2 - t_F
# is legal but likely a units or convention slip, so it is warned about.
MAX_UNREMARKED_FLOOD_DURATION = 2.0

__all__ = [
    "ACCEPTABLE_ERROR",
    "AGE_OF_EARTH",
    "FLOOD_AGE",
    "FLOOD_END_DATE",
    "FLOOD_START_AGE",
    "FLOOD_START_DATE",
    "ICE_AGE_END_AGE",
    "ICE_AGE_END_DATE",
    "LAMBDA_BG",
    "MAX_UNREMARKED_FLOOD_DURATION",
    "PRESENT_DATE",
    "SOLVER_TOLERANCE",
]
