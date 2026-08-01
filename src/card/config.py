"""
Run configuration: one YAML (or JSON) file describing a whole CARD fit.

A run config is the file form of what `examples/run_card_mcmc.py` hardcodes —
the chronology, the matched date pairs, which parameters are pinned, the
priors, and the sampler settings.  `card fit config.yaml` (see cli.py) reads it
and produces the same chain, figures and summary the driver script does, so
exploring a different chronology or a different constraint set is an edit to a
config file rather than an edit to a script.

Example::

    chronology:                 # optional; omitted means DEFAULT_CHRONOLOGY
      age_of_earth: 6056
      flood_start_date: 1656
      flood_end_date: 1656
      ice_age_end_date: 3500

    constraints:                # matched date pairs; young ages are AGEs
      - young_age: flood_start_age
        secular_age: 540e6
        uncertainty: 1.0e7
        label: Precambrian-Cambrian boundary
      - young_age: ice_age_end_age
        secular_age: 11500
        uncertainty: 30

    fixed:                      # linear units, whatever the sampling space
      lambda_c: 1.0
      k_c: 0.0
      t_c: 1.0
      t_F: flood_start_date
      t_F2: flood_end_date

    priors:                     # in each parameter's *sampling* space
      lambda_F: {mean: 6.0, sigma: 1.0}   # log-scale, so these are log10
      k_F: {mean: -3.0, sigma: 1.0}

    sampler:
      n_walkers: 32
      n_steps: 20000
      burn_in: 5000
      seed: 12345               # optional; makes a run reproducible

    output:
      directory: mcmc_output
      figures: true

TIME CONVENTIONS — the config obeys the package's naming rule, and that rule is
what makes the chronology keywords unambiguous.  Anywhere a number is expected
you may instead write the *name* of a chronology quantity: a name ending in
``_age`` resolves to an AGE (years before present) and one ending in ``_date``
to a DATE (years after Day 1 of Creation).  Writing ``t_F: flood_start_date``
is therefore self-checking in a way that ``t_F: 1656`` is not.

Unknown keys are rejected rather than ignored: a misspelled ``uncertianty``
would otherwise silently fall back to a default and change the posterior.
"""

import json
import os
from collections.abc import Mapping as MappingABC
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from .chronology import DEFAULT_CHRONOLOGY, Chronology

__all__ = [
    "Constraint",
    "RunConfig",
    "SamplerConfig",
    "load_config",
]

#: Sampler defaults.  Deliberately the driver script's production values, so a
#: config that omits `sampler:` reproduces `examples/run_card_mcmc.py`.
DEFAULT_N_WALKERS = 32
DEFAULT_N_STEPS = 20000
DEFAULT_BURN_IN = 5000


def _chronology_keywords(chronology: Chronology) -> Dict[str, float]:
    """
    Named chronology quantities usable anywhere a number is expected.

    The ``_age``/``_date`` suffix carries the convention, so a config that uses
    these names cannot mix the two up the way bare numbers can.
    """
    return {
        "age_of_earth": chronology.age_of_earth,
        "present_date": chronology.present_date,
        "creation_age": chronology.age_of_earth,
        "flood_start_date": chronology.flood_start_date,
        "flood_end_date": chronology.flood_end_date,
        "ice_age_end_date": chronology.ice_age_end_date,
        "flood_start_age": chronology.flood_start_age,
        "flood_age": chronology.flood_start_age,
        "flood_end_age": chronology.flood_end_age,
        "ice_age_end_age": chronology.ice_age_end_age,
    }


def _resolve(value: Any, chronology: Chronology, where: str) -> float:
    """Turn a config value — a number or a chronology keyword — into a float."""
    if isinstance(value, str):
        text = value.strip()
        keywords = _chronology_keywords(chronology)
        if text in keywords:
            return float(keywords[text])
        try:
            # YAML 1.1 does not read `540.0e6` as a float — it wants
            # `540.0e+6` — so numeric-looking strings are accepted rather than
            # rejected over a missing plus sign.
            return float(text)
        except ValueError:
            raise ValueError(
                f"{where}: {value!r} is not a number or a known chronology "
                f"name.  Known names are {sorted(keywords)}."
            ) from None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: expected a number, got {value!r}")
    return float(value)


def _require_mapping(value: Any, where: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, MappingABC):
        raise ValueError(f"{where}: expected a mapping, got {value!r}")
    return dict(value)


def _reject_unknown(data: Mapping[str, Any], known: Sequence[str],
                    where: str) -> None:
    unknown = set(data) - set(known)
    if unknown:
        raise ValueError(
            f"{where}: unrecognized key(s) {sorted(unknown)}; "
            f"expected any of {sorted(known)}."
        )


@dataclass(frozen=True)
class Constraint:
    """
    One matched date pair.

    Attributes:
        young_age: AGE (years before present) of the event.
        secular_age: Secular age the rock formed then should appear to have.
        uncertainty: Standard deviation on `secular_age`, in years.
        label: Optional human-readable name, used in printed output.
    """

    young_age: float
    secular_age: float
    uncertainty: float
    label: str = ""

    def as_tuple(self) -> Tuple[float, float, float]:
        """The ``(young_age, secular_age, uncertainty)`` triple MCMCFitter wants."""
        return (self.young_age, self.secular_age, self.uncertainty)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], chronology: Chronology,
                  where: str) -> "Constraint":
        data = _require_mapping(data, where)
        _reject_unknown(data, ("young_age", "secular_age", "uncertainty",
                               "label"), where)
        for required in ("young_age", "secular_age", "uncertainty"):
            if required not in data:
                raise ValueError(f"{where}: missing required key {required!r}")
        return cls(
            young_age=_resolve(data["young_age"], chronology,
                               f"{where}.young_age"),
            secular_age=_resolve(data["secular_age"], chronology,
                                 f"{where}.secular_age"),
            uncertainty=_resolve(data["uncertainty"], chronology,
                                 f"{where}.uncertainty"),
            label=str(data.get("label", "")),
        )


@dataclass(frozen=True)
class SamplerConfig:
    """emcee settings for a run."""

    n_walkers: int = DEFAULT_N_WALKERS
    n_steps: int = DEFAULT_N_STEPS
    burn_in: int = DEFAULT_BURN_IN
    seed: Optional[int] = None
    init_spread: float = 1e-4
    progress: bool = True

    def __post_init__(self):
        for name in ("n_walkers", "n_steps"):
            if getattr(self, name) < 1:
                raise ValueError(f"sampler.{name} must be positive, got "
                                 f"{getattr(self, name)!r}")
        if self.burn_in < 0:
            raise ValueError(f"sampler.burn_in must be >= 0, got "
                             f"{self.burn_in!r}")
        if self.init_spread <= 0:
            raise ValueError(f"sampler.init_spread must be positive, got "
                             f"{self.init_spread!r}")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SamplerConfig":
        data = _require_mapping(data, "sampler")
        _reject_unknown(data, [f for f in cls.__dataclass_fields__], "sampler")
        kwargs: Dict[str, Any] = {}
        for name in ("n_walkers", "n_steps", "burn_in"):
            if name in data:
                kwargs[name] = int(data[name])
        if data.get("seed") is not None:
            kwargs["seed"] = int(data["seed"])
        if "init_spread" in data:
            kwargs["init_spread"] = float(data["init_spread"])
        if "progress" in data:
            kwargs["progress"] = bool(data["progress"])
        return cls(**kwargs)


@dataclass(frozen=True)
class RunConfig:
    """
    A complete fit, described by data rather than by code.

    Attributes:
        chronology: Chronology the ages are measured against.
        constraints: Matched date pairs to fit.
        fixed_params: Parameters pinned to a value, in linear units.
        prior_means: Gaussian prior centers, in each parameter's sampling space.
        prior_sigmas: Gaussian prior widths, same spaces.
        sampler: emcee settings.
        output_dir: Directory for `chain.h5`, figures and the summary.
        figures: Whether `card fit` writes figures as well as the chain.
    """

    constraints: Tuple[Constraint, ...]
    chronology: Chronology = DEFAULT_CHRONOLOGY
    fixed_params: Dict[str, float] = field(default_factory=dict)
    prior_means: Dict[str, float] = field(default_factory=dict)
    prior_sigmas: Dict[str, float] = field(default_factory=dict)
    sampler: SamplerConfig = field(default_factory=SamplerConfig)
    output_dir: str = "mcmc_output"
    figures: bool = True

    def __post_init__(self):
        if not self.constraints:
            raise ValueError(
                "A run config needs at least one constraint: a matched date "
                "pair of a young AGE and the secular age it should appear."
            )

    # ------------------------------------------------------------- loading
    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunConfig":
        """
        Build from an already-parsed config mapping.

        Raises:
            ValueError: On unknown keys, missing constraints, or a value that
                is neither a number nor a chronology keyword.
        """
        data = _require_mapping(data, "config")
        _reject_unknown(data, ("chronology", "constraints", "fixed", "priors",
                               "sampler", "output"), "config")

        chronology = (Chronology.from_dict(_require_mapping(
            data["chronology"], "chronology"))
            if data.get("chronology") is not None else DEFAULT_CHRONOLOGY)

        raw_constraints = data.get("constraints")
        if not isinstance(raw_constraints, SequenceABC) or isinstance(
                raw_constraints, (str, bytes)):
            raise ValueError(
                "config.constraints must be a list of matched date pairs, got "
                f"{raw_constraints!r}"
            )
        constraints = tuple(
            Constraint.from_dict(row, chronology, f"constraints[{i}]")
            for i, row in enumerate(raw_constraints)
        )

        fixed = {
            name: _resolve(value, chronology, f"fixed.{name}")
            for name, value in _require_mapping(data.get("fixed"),
                                                "fixed").items()
        }

        prior_means: Dict[str, float] = {}
        prior_sigmas: Dict[str, float] = {}
        for name, spec in _require_mapping(data.get("priors"),
                                           "priors").items():
            where = f"priors.{name}"
            spec = _require_mapping(spec, where)
            _reject_unknown(spec, ("mean", "sigma"), where)
            if "mean" in spec:
                prior_means[name] = _resolve(spec["mean"], chronology,
                                             f"{where}.mean")
            if "sigma" in spec:
                sigma = _resolve(spec["sigma"], chronology, f"{where}.sigma")
                if sigma <= 0:
                    raise ValueError(
                        f"{where}.sigma must be positive, got {sigma!r}")
                prior_sigmas[name] = sigma

        output = _require_mapping(data.get("output"), "output")
        _reject_unknown(output, ("directory", "figures"), "output")

        return cls(
            constraints=constraints,
            chronology=chronology,
            fixed_params=fixed,
            prior_means=prior_means,
            prior_sigmas=prior_sigmas,
            sampler=SamplerConfig.from_dict(data.get("sampler")),
            output_dir=str(output.get("directory", "mcmc_output")),
            figures=bool(output.get("figures", True)),
        )

    @classmethod
    def from_file(cls, path: str) -> "RunConfig":
        """
        Load a config from a ``.yaml``/``.yml`` or ``.json`` file.

        Raises:
            FileNotFoundError: If `path` does not exist.
            ValueError: If the suffix is not recognized, the file does not
                parse, or the contents fail validation.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"No run config at {path!r}")

        suffix = os.path.splitext(path)[1].lower()
        with open(path) as handle:
            if suffix in (".yaml", ".yml"):
                try:
                    import yaml
                except ImportError:  # pragma: no cover - depends on install
                    raise ValueError(
                        "Reading a YAML config needs PyYAML "
                        "(`pip install pyyaml`), or write the config as JSON."
                    ) from None
                data = yaml.safe_load(handle)
            elif suffix == ".json":
                data = json.load(handle)
            else:
                raise ValueError(
                    f"Unrecognized config format {suffix!r} for {path!r}; "
                    "expected .yaml, .yml or .json."
                )

        if data is None:
            raise ValueError(f"{path!r} is empty.")
        return cls.from_dict(data)

    # -------------------------------------------------------------- using
    def build_fitter(self):
        """
        Construct the `MCMCFitter` this config describes.

        The chronology is passed through as `present_time`, so a non-default
        chronology governs the forward ages as well as the constraint ages.
        """
        from .inference import MCMCFitter

        return MCMCFitter(
            [c.as_tuple() for c in self.constraints],
            prior_means=self.prior_means or None,
            prior_sigmas=self.prior_sigmas or None,
            fixed_params=self.fixed_params or None,
            present_time=self.chronology.present_date,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Round-trippable plain-dict form (all keywords resolved to numbers)."""
        return {
            "chronology": self.chronology.to_dict(),
            "constraints": [
                {"young_age": c.young_age, "secular_age": c.secular_age,
                 "uncertainty": c.uncertainty, "label": c.label}
                for c in self.constraints
            ],
            "fixed": dict(self.fixed_params),
            "priors": {
                name: {"mean": self.prior_means.get(name),
                       "sigma": self.prior_sigmas.get(name)}
                for name in sorted(set(self.prior_means) | set(self.prior_sigmas))
            },
            "sampler": {
                "n_walkers": self.sampler.n_walkers,
                "n_steps": self.sampler.n_steps,
                "burn_in": self.sampler.burn_in,
                "seed": self.sampler.seed,
                "init_spread": self.sampler.init_spread,
                "progress": self.sampler.progress,
            },
            "output": {"directory": self.output_dir, "figures": self.figures},
        }


def load_config(path: str) -> RunConfig:
    """Load a run config from a YAML or JSON file.  See `RunConfig.from_file`."""
    return RunConfig.from_file(path)
