"""
CARD — Calibrating Accelerated Radiometric Decay.

Models time-varying (accelerated) radiometric decay rates and converts
between true (young-earth) ages and apparent (secular) ages, with MCMC
fitting of model parameters to age constraints.
"""

from .chronology import DEFAULT_CHRONOLOGY, Chronology
from .decay_solver import (
    ACCEPTABLE_ERROR,
    AGE_OF_EARTH,
    FLOOD_AGE,
    FLOOD_END_DATE,
    FLOOD_START_AGE,
    FLOOD_START_DATE,
    ICE_AGE_END_AGE,
    ICE_AGE_END_DATE,
    LAMBDA_BG,
    PRESENT_DATE,
    ConstantDecayModel,
    DecayModel,
    GeneralModel,
    GeneralModelParams,
    plot_age_comparison,
    plot_general_model_parameter_sweep,
    years_after_creation_to_years_before_present,
    years_before_present_to_years_after_creation,
)
from .card_mcmc import CARDMCMC

__version__ = "0.1.0"
