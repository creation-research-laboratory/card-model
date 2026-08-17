"""
Parameter metadata: one declaration, many consumers.

Each model parameter is described exactly once, on the dataclass field that
holds it, by a `ParamSpec`.  Everything that needs to know about parameters
reads that declaration instead of carrying its own copy:

  * `card.inference` — which parameters are free, whether to sample them in
    log10, and what the default priors are.
  * `card.plotting` — axis labels and whether an axis should be logarithmic.
  * a GUI — slider bounds, scale, units, and tooltips.
  * a browser calculator — a JSON schema for the input form.

Before this existed, the parameter list was written out by hand in the MCMC
fitter, the sweep plots, and the driver scripts, and the three could disagree.

Attach specs with `dataclasses.field(metadata={"spec": ParamSpec(...)})` and
read them back with `parameter_specs(SomeParamsClass)`.
"""

from dataclasses import dataclass, fields
from typing import Any, Dict, Mapping, Tuple

__all__ = [
    "ParamSpec",
    "parameter_bounds",
    "parameter_defaults",
    "parameter_names",
    "parameter_specs",
    "structural_names",
    "to_json_schema",
]

#: Key under which a ParamSpec is stored in a dataclass field's metadata.
SPEC_KEY = "spec"


@dataclass(frozen=True)
class ParamSpec:
    """
    Everything a consumer needs to know about one model parameter.

    Attributes:
        symbol: LaTeX symbol, e.g. ``r"\\lambda_F"``.  Used for plot labels.
        unit: Physical unit, or "" when the quantity is dimensionless.
        description: One line of prose, suitable for a tooltip.
        default: A sensible starting value.
        minimum: Smallest value the model accepts.
        maximum: Largest value worth exploring.  This is a practical bound for
            sliders and priors, not a hard validity limit.
        log_scale: True when the parameter spans orders of magnitude.  Such
            parameters are sampled in log10 by the fitter and drawn on log axes;
            their priors are specified in log10 units.
        is_date: True when the parameter is a DATE — years after Day 1 of
            Creation.  Its upper bound is then the age of the Earth, which is a
            chronology setting rather than a constant, so a consumer building
            sliders should ask `bounds_for_chronology` instead of reading
            `maximum` directly.
    """

    symbol: str
    unit: str
    description: str
    default: float
    minimum: float
    maximum: float
    log_scale: bool = False
    is_date: bool = False

    def clamp(self, value: float) -> float:
        """Clamp a value into [minimum, maximum] — useful for GUI inputs."""
        return min(max(value, self.minimum), self.maximum)

    def contains(self, value: float) -> bool:
        """True when `value` lies within the advertised range."""
        return self.minimum <= value <= self.maximum

    @property
    def is_fittable(self) -> bool:
        """
        False for parameters pinned by definition rather than by choice.

        A degenerate range (minimum == maximum) marks a quantity that is not
        free to vary — `lambda_bg` is always 1 because every other rate is
        normalized against it — so fitters and sliders skip it automatically
        instead of each maintaining its own exclusion list.
        """
        return self.minimum < self.maximum


def parameter_specs(params_class: Any) -> Dict[str, ParamSpec]:
    """
    Map field name -> ParamSpec for a parameter dataclass.

    Fields without a spec are omitted, so a class can carry bookkeeping fields
    that are not user-facing parameters.
    """
    return {
        f.name: f.metadata[SPEC_KEY]
        for f in fields(params_class)
        if SPEC_KEY in f.metadata
    }


def parameter_names(params_class: Any) -> Tuple[str, ...]:
    """Names of the specified parameters, in declaration order."""
    return tuple(parameter_specs(params_class))


def fittable_names(params_class: Any) -> Tuple[str, ...]:
    """Names of parameters that are free to vary (see `ParamSpec.is_fittable`)."""
    return tuple(name for name, spec in parameter_specs(params_class).items()
                 if spec.is_fittable)


def parameter_defaults(params_class: Any) -> Dict[str, float]:
    """Default value for each specified parameter."""
    return {name: spec.default
            for name, spec in parameter_specs(params_class).items()}


def parameter_bounds(params_class: Any) -> Dict[str, Tuple[float, float]]:
    """(minimum, maximum) for each specified parameter."""
    return {name: (spec.minimum, spec.maximum)
            for name, spec in parameter_specs(params_class).items()}


def bounds_for_chronology(params_class: Any,
                          chronology: Any) -> Dict[str, Tuple[float, float]]:
    """
    (minimum, maximum) per parameter, with DATE bounds taken from `chronology`.

    The declared bounds are fixed at import time against the default
    chronology, so a caller that lets the user change the age of the Earth —
    a GUI, a browser form — would otherwise offer date sliders that stop at
    6056 years no matter what chronology is loaded.  Everything that is not a
    DATE is returned unchanged.

    Args:
        params_class: Parameter dataclass carrying ParamSpec metadata.
        chronology: A `Chronology`; its `present_date` becomes the upper bound
            of every date parameter.

    Returns:
        Mapping of parameter name to (minimum, maximum).
    """
    present = float(chronology.present_date)
    return {
        name: (spec.minimum, present if spec.is_date else spec.maximum)
        for name, spec in parameter_specs(params_class).items()
    }


def to_json_schema(params_class: Any, title: str = None,
                   chronology: Any = None) -> Dict[str, Any]:
    """
    Render the parameter specs as a JSON Schema object.

    Intended for a browser front end, which can build and validate an input
    form from this without any Python.

    Args:
        params_class: Parameter dataclass carrying ParamSpec metadata.
        title: Schema title; defaults to the class name.
        chronology: Optional `Chronology`.  When given, DATE parameters get
            their upper bound from it (see `bounds_for_chronology`) instead of
            from the default chronology baked in at import time.
    """
    specs = parameter_specs(params_class)
    bounds = (bounds_for_chronology(params_class, chronology)
              if chronology is not None else parameter_bounds(params_class))
    return {
        "title": title or params_class.__name__,
        "type": "object",
        "properties": {
            name: {
                "type": "number",
                "title": spec.symbol,
                "description": spec.description,
                "default": spec.default,
                "minimum": bounds[name][0],
                "maximum": bounds[name][1],
                "x-unit": spec.unit,
                "x-log-scale": spec.log_scale,
                "x-is-date": spec.is_date,
            }
            for name, spec in specs.items()
        },
        "required": list(specs),
    }


def structural_names(params_class: Any) -> Tuple[str, ...]:
    """
    Fields that exist on the model but carry no ParamSpec.

    These are settable but never *fitted* — `t_F2`, whose value is the Flood's
    length and therefore a chronology assumption rather than something to infer
    from age constraints.  A config may pin them; nothing offers them as free.
    """
    specified = set(parameter_specs(params_class))
    return tuple(f.name for f in fields(params_class)
                 if f.name not in specified)


def split_fixed_and_free(
    params_class: Any, fixed_params: Mapping[str, float] = None
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """
    Split a parameter set into (free, fixed) names, validating the fixed keys.

    Structural fields (see `structural_names`) may appear in `fixed_params` and
    are returned among the fixed names, but never among the free ones — pinning
    `t_F2` is legal, fitting it is not.

    Raises:
        ValueError: If `fixed_params` names something the model does not have.
    """
    names = parameter_names(params_class)
    settable = names + structural_names(params_class)
    fixed_params = fixed_params or {}
    unknown = set(fixed_params) - set(settable)
    if unknown:
        raise ValueError(
            f"Unrecognized parameter name(s) {sorted(unknown)}; "
            f"expected any of {sorted(settable)}."
        )
    free = tuple(n for n in names if n not in fixed_params)
    fixed = tuple(n for n in settable if n in fixed_params)
    return free, fixed
