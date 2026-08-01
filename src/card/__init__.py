"""
CARD — Calibrating Accelerated Radiometric Decay.

Models time-varying (accelerated) radiometric decay rates and converts between
true (young-earth) ages and apparent (secular) ages, with MCMC fitting of model
parameters to age constraints.

    >>> from card import GeneralModel, FLOOD_AGE
    >>> model = GeneralModel.flood_only(lambda_F=3.2e6, k_F=6e-3)
    >>> round(model.forward_age(FLOOD_AGE))
    533337567

Layout::

    card.chronology  — Chronology config; DATE/AGE conversions
    card.constants   — numerical settings and chronology conveniences
    card.config      — YAML/JSON run configs (the `card fit` entry point)
    card.cli         — the `card` command-line interface
    card.parameters  — ParamSpec metadata consumed by fitters, plots and GUIs
    card.models      — DecayModel, ConstantDecayModel, GeneralModel, params
    card.calibrate   — deterministic solves from matched date pairs
    card.inference   — Bayesian fitting with emcee (HDF5 results)
    card.plotting    — figure generation (matplotlib)

**Imports are lazy.**  Every public name below resolves on first attribute
access rather than at `import card`, so pulling in the numerical core does not
drag in matplotlib, emcee or corner.  That keeps `import card` cheap and lets a
browser or headless build use the models without a plotting stack installed.
`from card import GeneralModel` works exactly as it would with eager imports.
"""

import importlib
from typing import TYPE_CHECKING

__version__ = "0.1.0"

# Public name -> module that defines it.  Adding a name here is all that is
# needed to export it lazily.
_EXPORTS = {
    # chronology
    "Chronology": "card.chronology",
    "DEFAULT_CHRONOLOGY": "card.chronology",
    "years_after_creation_to_years_before_present": "card.chronology",
    "years_before_present_to_years_after_creation": "card.chronology",
    # constants
    "ACCEPTABLE_ERROR": "card.constants",
    "AGE_OF_EARTH": "card.constants",
    "FLOOD_AGE": "card.constants",
    "FLOOD_END_DATE": "card.constants",
    "FLOOD_START_AGE": "card.constants",
    "FLOOD_START_DATE": "card.constants",
    "ICE_AGE_END_AGE": "card.constants",
    "ICE_AGE_END_DATE": "card.constants",
    "LAMBDA_BG": "card.constants",
    "MAX_UNREMARKED_FLOOD_DURATION": "card.constants",
    "PRESENT_DATE": "card.constants",
    "SOLVER_TOLERANCE": "card.constants",
    # run configuration (YAML/JSON) — see also the `card` CLI
    "Constraint": "card.config",
    "RunConfig": "card.config",
    "SamplerConfig": "card.config",
    "example_config_text": "card.config",
    "load_config": "card.config",
    # models
    "ConstantDecayModel": "card.models",
    "DecayModel": "card.models",
    "GeneralModel": "card.models",
    "GeneralModelParams": "card.models",
    # parameter metadata
    "ParamSpec": "card.parameters",
    "parameter_bounds": "card.parameters",
    "parameter_defaults": "card.parameters",
    "parameter_names": "card.parameters",
    "parameter_specs": "card.parameters",
    "to_json_schema": "card.parameters",
    # deterministic calibration
    "CalibrationResult": "card.calibrate",
    "solve_flood_only": "card.calibrate",
    "solve_lambda_F": "card.calibrate",
    # plotting (matplotlib)
    "load_legacy_text_results": "card.plotting",
    "plot_age_comparison": "card.plotting",
    "plot_general_model_parameter_sweep": "card.plotting",
    "plot_lambda_history": "card.plotting",
    "plot_mcmc_corner": "card.plotting",
    "plot_mcmc_traces": "card.plotting",
    "summarize_mcmc": "card.plotting",
    # inference (emcee, h5py)
    "MCMCFitter": "card.inference",
    "load_results": "card.inference",
    "save_results": "card.inference",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    """Resolve a public name on first access (PEP 562)."""
    try:
        module_name = _EXPORTS[name]
    except KeyError:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from None
    value = getattr(importlib.import_module(module_name), name)
    # Cache on the module so subsequent lookups skip __getattr__ entirely.
    globals()[name] = value
    return value


def __dir__():
    return sorted([*__all__, "__version__"])


# Give type checkers and IDEs the real names; this block never runs.
if TYPE_CHECKING:  # pragma: no cover
    from .calibrate import (
        CalibrationResult,
        solve_flood_only,
        solve_lambda_F,
    )
    from .chronology import (
        DEFAULT_CHRONOLOGY,
        Chronology,
        years_after_creation_to_years_before_present,
        years_before_present_to_years_after_creation,
    )
    from .config import (
        Constraint,
        RunConfig,
        SamplerConfig,
        example_config_text,
        load_config,
    )
    from .constants import (
        ACCEPTABLE_ERROR,
        AGE_OF_EARTH,
        FLOOD_AGE,
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
    from .inference import MCMCFitter, load_results, save_results
    from .models import (
        ConstantDecayModel,
        DecayModel,
        GeneralModel,
        GeneralModelParams,
    )
    from .parameters import (
        ParamSpec,
        parameter_bounds,
        parameter_defaults,
        parameter_names,
        parameter_specs,
        to_json_schema,
    )
    from .plotting import (
        load_legacy_text_results,
        plot_age_comparison,
        plot_general_model_parameter_sweep,
        plot_lambda_history,
        plot_mcmc_corner,
        plot_mcmc_traces,
        summarize_mcmc,
    )
