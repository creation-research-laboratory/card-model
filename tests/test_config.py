"""
Tests for the YAML/JSON run configuration.

The config file is the only place a user describes a fit without writing
Python, so the things worth pinning here are the ones a silent default would
hide: that a misspelled key is rejected rather than ignored, that the
chronology keywords resolve on the right side of the DATE/AGE divide, and that
a non-default chronology reaches the fitter's `present_time` instead of being
read for the constraint ages only.
"""

import json

import pytest
import yaml

from card import Chronology, RunConfig, SamplerConfig, load_config

MINIMAL = {
    "constraints": [
        {"young_age": "flood_start_age", "secular_age": 540e6,
         "uncertainty": 1e7},
        {"young_age": "ice_age_end_age", "secular_age": 11500.0,
         "uncertainty": 30.0},
    ],
    "fixed": {"lambda_c": 1.0, "k_c": 0.0, "t_c": 1.0,
              "t_F": "flood_start_date", "t_F2": "flood_end_date"},
    "priors": {"lambda_F": {"mean": 6.0, "sigma": 1.0},
               "k_F": {"mean": -3.0, "sigma": 1.0}},
}


def write(tmp_path, data, name="run.yaml"):
    path = tmp_path / name
    if name.endswith(".json"):
        path.write_text(json.dumps(data))
    else:
        path.write_text(yaml.safe_dump(data))
    return str(path)


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------

def test_minimal_config_parses():
    config = RunConfig.from_dict(MINIMAL)
    assert len(config.constraints) == 2
    assert config.fixed_params["lambda_c"] == 1.0
    assert config.prior_means == {"lambda_F": 6.0, "k_F": -3.0}
    assert config.output_dir == "mcmc_output"


def test_yaml_and_json_agree(tmp_path):
    from_yaml = load_config(write(tmp_path, MINIMAL, "run.yaml"))
    from_json = load_config(write(tmp_path, MINIMAL, "run.json"))
    assert from_yaml.to_dict() == from_json.to_dict()


def test_shipped_example_config_loads():
    """examples/flood_only.yaml is the documented entry point; keep it valid."""
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = load_config(os.path.join(root, "examples", "flood_only.yaml"))
    assert config.chronology == Chronology()
    assert [c.young_age for c in config.constraints] == [4400.0, 2556.0]
    assert config.sampler.seed is not None  # the example must be reproducible


def test_chronology_keywords_respect_the_date_age_rule():
    """`*_age` resolves to years before present, `*_date` to years after
    Creation; the two must not come out equal."""
    config = RunConfig.from_dict(MINIMAL)
    flood = config.constraints[0]
    assert flood.young_age == 4400.0            # AGE
    assert config.fixed_params["t_F"] == 1656.0  # DATE
    assert flood.young_age + config.fixed_params["t_F"] == 6056.0


def test_keywords_follow_a_custom_chronology():
    data = dict(MINIMAL, chronology={"age_of_earth": 7000.0,
                                     "flood_start_date": 2000.0,
                                     "flood_end_date": 2000.0,
                                     "ice_age_end_date": 3600.0})
    config = RunConfig.from_dict(data)
    assert config.constraints[0].young_age == 5000.0
    assert config.constraints[1].young_age == 3400.0
    assert config.fixed_params["t_F"] == 2000.0


def test_numeric_strings_are_accepted(tmp_path):
    """YAML 1.1 reads `540.0e6` as a string, not a float, because it lacks the
    plus sign.  Rejecting that would be a trap, not a safety feature."""
    path = tmp_path / "run.yaml"
    path.write_text(
        "constraints:\n"
        "  - young_age: flood_start_age\n"
        "    secular_age: 540.0e6\n"
        "    uncertainty: 1.0e7\n"
    )
    config = load_config(str(path))
    assert config.constraints[0].secular_age == 540e6


def test_sampler_defaults_match_the_driver():
    config = RunConfig.from_dict(MINIMAL)
    assert (config.sampler.n_walkers, config.sampler.n_steps,
            config.sampler.burn_in) == (32, 20000, 5000)
    assert config.sampler.seed is None


# ----------------------------------------------------------------------------
# Validation — a config typo must be loud
# ----------------------------------------------------------------------------

def test_unknown_top_level_key_is_rejected():
    with pytest.raises(ValueError, match="unrecognized key"):
        RunConfig.from_dict(dict(MINIMAL, smapler={"n_steps": 10}))


def test_unknown_constraint_key_is_rejected():
    bad = dict(MINIMAL, constraints=[
        {"young_age": 4400.0, "secular_age": 540e6, "uncertianty": 1e7}])
    with pytest.raises(ValueError, match="unrecognized key"):
        RunConfig.from_dict(bad)


def test_missing_constraint_key_is_rejected():
    bad = dict(MINIMAL, constraints=[{"young_age": 4400.0,
                                      "secular_age": 540e6}])
    with pytest.raises(ValueError, match="missing required key"):
        RunConfig.from_dict(bad)


def test_unknown_chronology_keyword_names_the_alternatives():
    bad = dict(MINIMAL, constraints=[
        {"young_age": "flood", "secular_age": 540e6, "uncertainty": 1e7}])
    with pytest.raises(ValueError, match="known chronology name"):
        RunConfig.from_dict(bad)


def test_no_constraints_is_rejected():
    with pytest.raises(ValueError, match="at least one constraint"):
        RunConfig.from_dict(dict(MINIMAL, constraints=[]))


def test_non_positive_prior_sigma_is_rejected():
    bad = dict(MINIMAL, priors={"lambda_F": {"mean": 6.0, "sigma": 0.0}})
    with pytest.raises(ValueError, match="sigma must be positive"):
        RunConfig.from_dict(bad)


@pytest.mark.parametrize("sampler, match", [
    ({"n_walkers": 0}, "n_walkers must be positive"),
    ({"n_steps": -1}, "n_steps must be positive"),
    ({"burn_in": -5}, "burn_in must be >= 0"),
])
def test_bad_sampler_settings_are_rejected(sampler, match):
    with pytest.raises(ValueError, match=match):
        RunConfig.from_dict(dict(MINIMAL, sampler=sampler))


def test_unknown_format_is_rejected(tmp_path):
    path = tmp_path / "run.toml"
    path.write_text("nope")
    with pytest.raises(ValueError, match="Unrecognized config format"):
        load_config(str(path))


def test_missing_file_says_so(tmp_path):
    with pytest.raises(FileNotFoundError, match="No run config"):
        load_config(str(tmp_path / "absent.yaml"))


def test_empty_file_says_so(tmp_path):
    path = tmp_path / "run.yaml"
    path.write_text("")
    with pytest.raises(ValueError, match="is empty"):
        load_config(str(path))


# ----------------------------------------------------------------------------
# Handing off to the fitter
# ----------------------------------------------------------------------------

def test_build_fitter_frees_the_unpinned_parameters():
    fitter = RunConfig.from_dict(MINIMAL).build_fitter()
    assert fitter.free_param_names == ("lambda_F", "k_F")
    assert fitter.prior_means["lambda_F"] == 6.0


def test_custom_chronology_reaches_present_time():
    """Otherwise the constraint ages would come from the config's chronology
    while forward_age measured them against the default one."""
    data = dict(MINIMAL, chronology={"age_of_earth": 7000.0,
                                     "flood_start_date": 2000.0,
                                     "flood_end_date": 2000.0,
                                     "ice_age_end_date": 3600.0})
    fitter = RunConfig.from_dict(data).build_fitter()
    assert fitter.present_time == 7000.0


def test_to_dict_round_trips():
    config = RunConfig.from_dict(MINIMAL)
    assert RunConfig.from_dict(config.to_dict()).to_dict() == config.to_dict()


def test_sampler_config_is_replaceable():
    """`card fit --steps N` overrides by dataclasses.replace, so the sampler
    settings must stay a plain frozen dataclass."""
    import dataclasses

    sampler = dataclasses.replace(SamplerConfig(), n_steps=10)
    assert sampler.n_steps == 10 and sampler.n_walkers == 32
