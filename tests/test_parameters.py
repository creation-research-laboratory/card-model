"""
Tests for the parameter spec — the single declaration that the fitter,
the plots, and any GUI all read instead of keeping their own copies.
"""

import pytest

from card import GeneralModelParams, ParamSpec
from card.parameters import (
    fittable_names,
    parameter_bounds,
    parameter_defaults,
    parameter_names,
    parameter_specs,
    split_fixed_and_free,
    to_json_schema,
)


def test_every_model_parameter_has_a_spec():
    specs = parameter_specs(GeneralModelParams)
    assert set(specs) == {"lambda_c", "lambda_F", "lambda_bg",
                          "k_c", "k_F", "t_c", "t_F", "t_F2"}


def test_specs_are_consistent_with_validation():
    """The advertised minima must agree with what __post_init__ enforces:
    rates >= 1, relaxation constants >= 0, dates >= 0."""
    specs = parameter_specs(GeneralModelParams)
    assert specs["lambda_c"].minimum == 1.0
    assert specs["lambda_F"].minimum == 1.0
    assert specs["k_c"].minimum == 0.0
    assert specs["k_F"].minimum == 0.0
    for name in ("t_c", "t_F", "t_F2"):
        assert specs[name].minimum == 0.0


def test_defaults_construct_a_valid_model():
    params = GeneralModelParams.defaults()
    assert params.lambda_bg == 1.0
    assert params.t_F == params.t_F2  # instantaneous Flood by default


def test_defaults_accept_overrides():
    params = GeneralModelParams.defaults(lambda_F=1e6, k_F=1e-2)
    assert params.lambda_F == 1e6
    assert params.k_F == 1e-2


def test_defaults_reject_unknown_names():
    with pytest.raises(ValueError, match="Unrecognized parameter"):
        GeneralModelParams.defaults(lambda_typo=1.0)


def test_every_default_is_inside_its_own_bounds():
    for name, spec in parameter_specs(GeneralModelParams).items():
        assert spec.contains(spec.default), name


def test_scale_flags_match_the_physics():
    """Rates and relaxation constants span orders of magnitude; dates do not."""
    specs = parameter_specs(GeneralModelParams)
    for name in ("lambda_c", "lambda_F", "k_c", "k_F"):
        assert specs[name].log_scale is True, name
    for name in ("t_c", "t_F", "t_F2"):
        assert specs[name].log_scale is False, name


def test_lambda_bg_is_not_fittable():
    """It is 1 by definition — every other rate is normalized against it — so
    fitters and sliders must skip it without maintaining their own list."""
    specs = parameter_specs(GeneralModelParams)
    assert specs["lambda_bg"].is_fittable is False
    assert "lambda_bg" not in fittable_names(GeneralModelParams)
    assert len(fittable_names(GeneralModelParams)) == 7


def test_clamp_keeps_values_in_range():
    spec = parameter_specs(GeneralModelParams)["lambda_F"]
    assert spec.clamp(-5) == spec.minimum
    assert spec.clamp(1e30) == spec.maximum
    assert spec.clamp(1e5) == 1e5


def test_bounds_and_defaults_cover_all_parameters():
    names = parameter_names(GeneralModelParams)
    assert set(parameter_bounds(GeneralModelParams)) == set(names)
    assert set(parameter_defaults(GeneralModelParams)) == set(names)


def test_split_fixed_and_free():
    free, fixed = split_fixed_and_free(GeneralModelParams,
                                       {"t_F": 1656.0, "t_F2": 1656.0})
    assert set(fixed) == {"t_F", "t_F2"}
    assert "lambda_F" in free and "t_F" not in free


def test_split_rejects_unknown_fixed_names():
    with pytest.raises(ValueError, match="Unrecognized parameter"):
        split_fixed_and_free(GeneralModelParams, {"lambda_typo": 1.0})


def test_json_schema_is_usable_by_a_front_end():
    schema = to_json_schema(GeneralModelParams, title="CARD general model")
    assert schema["title"] == "CARD general model"
    lam = schema["properties"]["lambda_F"]
    assert lam["type"] == "number"
    assert lam["minimum"] == 1.0
    assert lam["x-log-scale"] is True
    assert set(schema["required"]) == set(parameter_names(GeneralModelParams))


def test_spec_is_immutable():
    spec = parameter_specs(GeneralModelParams)["k_F"]
    with pytest.raises(Exception):
        spec.default = 1.0


def test_specs_are_reachable_from_the_class():
    assert GeneralModelParams.specs() == parameter_specs(GeneralModelParams)
    assert GeneralModelParams.names() == parameter_names(GeneralModelParams)
    assert isinstance(GeneralModelParams.specs()["k_F"], ParamSpec)
