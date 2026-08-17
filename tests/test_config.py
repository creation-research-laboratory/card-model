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

import numpy as np
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
    "fixed": {"lambda_c": 1.0, "k_c": 0.0, "k_F": 0.0, "t_c": 1.0,
              "t_F": "flood_start_date", "t_F2": "flood_end_date"},
    "priors": {"lambda_F": {"mean": 6.0, "sigma": 1.0},
               "k_PF": {"mean": -3.0, "sigma": 1.0}},
}

#: The three-pair form: k_F is fitted, so it is absent from `fixed`.
_THREE_PAIR_FIXED = {"lambda_c": 1.0, "k_c": 0.0, "t_c": 1.0,
                     "t_F": "flood_start_date", "t_F2": "flood_end_date"}


def _three_pair_config(**overrides):
    """MINIMAL with the Flood's end added as a third pair."""
    data = {
        "constraints": [
            {"young_age": "flood_start_age", "secular_age": 540e6,
             "uncertainty": 1e7},
            {"young_age": "flood_end_age", "secular_age": 66e6,
             "uncertainty": 1e5},
            {"young_age": "ice_age_end_age", "secular_age": 11500.0,
             "uncertainty": 30.0},
        ],
        "fixed": dict(_THREE_PAIR_FIXED),
        "priors": {"lambda_F": {"mean": 9.7, "sigma": 1.0},
                   "k_F": {"mean": 9.6, "sigma": 5.0},
                   "k_PF": {"mean": -2.3, "sigma": 1.0}},
    }
    data.update(overrides)
    return data


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
    assert config.prior_means == {"lambda_F": 6.0, "k_PF": -3.0}
    assert config.output_dir == "mcmc_output"


def test_yaml_and_json_agree(tmp_path):
    from_yaml = load_config(write(tmp_path, MINIMAL, "run.yaml"))
    from_json = load_config(write(tmp_path, MINIMAL, "run.json"))
    assert from_yaml.to_dict() == from_json.to_dict()


def test_bundled_example_config_loads(tmp_path):
    """The example ships as package data — `examples/` is not installed, so a
    pip user has no repository to point at.  It is what `card init` writes, so
    it must stay valid."""
    from card.config import example_config_text

    path = tmp_path / "bundled.yaml"
    path.write_text(example_config_text())

    config = load_config(str(path))
    assert config.chronology == Chronology()
    # Three pairs: the Flood's onset, its end one year later, and the Ice Age.
    assert [c.young_age for c in config.constraints] == [4400.0, 4399.0, 2556.0]
    # k_F is what the third pair buys, so the shipped config must not pin it.
    assert "k_F" not in config.fixed_params
    assert config.sampler.seed is not None       # must be reproducible
    assert config.sampler.initial_guess == "calibrate"  # must not get stuck


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
    assert fitter.free_param_names == ("lambda_F", "k_PF")
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


def test_initial_guess_defaults_to_none():
    fitter = RunConfig.from_dict(MINIMAL).build_fitter()
    assert RunConfig.from_dict(MINIMAL).initial_guess_for(fitter) is None


def test_calibrate_keyword_starts_at_the_exact_solution():
    """In sampling space, so log10 for these two — the conversion is the whole
    point of resolving the guess against the fitter rather than the config."""
    from card import solve_flood_only

    config = RunConfig.from_dict(
        dict(MINIMAL, sampler={"initial_guess": "calibrate"}))
    guess = config.initial_guess_for(config.build_fitter())

    truth = solve_flood_only(4400.0, 540e6, 2556.0, 11500.0)
    assert guess == pytest.approx([np.log10(truth.lambda_F),
                                   np.log10(truth.k_PF)])


def test_calibrate_keyword_needs_two_or_three_constraints():
    config = RunConfig.from_dict(dict(
        MINIMAL, constraints=MINIMAL["constraints"][:1],
        sampler={"initial_guess": "calibrate"}))
    with pytest.raises(ValueError, match="two matched date pairs"):
        config.initial_guess_for(config.build_fitter())


def test_calibrate_keyword_solves_three_pairs_including_k_F():
    """Three pairs determine k_F, so the starting position must include it —
    and linearly, because k_F is the one rate not sampled in log10."""
    from card import solve_flood_rate

    config = RunConfig.from_dict(_three_pair_config(
        sampler={"initial_guess": "calibrate"}))
    fitter = config.build_fitter()
    assert fitter.free_param_names == ("lambda_F", "k_F", "k_PF")

    truth = solve_flood_rate(540e6, 66e6, 11500.0)
    assert config.initial_guess_for(fitter) == pytest.approx(
        [np.log10(truth.lambda_F), truth.k_F, np.log10(truth.k_PF)])


def test_three_pairs_reject_a_pinned_k_F():
    config = RunConfig.from_dict(_three_pair_config(
        fixed=dict(_THREE_PAIR_FIXED, k_F=0.0)))
    with pytest.raises(ValueError, match="also pins it"):
        config.solve_exactly()


def test_three_pairs_reject_a_pair_aimed_elsewhere():
    """`solve_flood_rate` takes all three AGEs from the chronology, so a pair
    sitting somewhere else would be solved as a problem the file never
    described.  It must be refused, not silently relocated."""
    data = _three_pair_config()
    data["constraints"][1] = dict(data["constraints"][1], young_age=4000.0)
    with pytest.raises(ValueError, match="the Flood's end"):
        RunConfig.from_dict(data).solve_exactly()


def test_two_pairs_still_solve_at_a_pinned_k_F():
    """The two-pair solve is not superseded — it is what you use when k_F is
    known rather than fitted."""
    from card import solve_flood_only

    config = RunConfig.from_dict(MINIMAL)
    result = config.solve_exactly()
    truth = solve_flood_only(4400.0, 540e6, 2556.0, 11500.0)
    assert result.lambda_F == pytest.approx(truth.lambda_F)
    assert result.k_F == 0.0


def test_explicit_initial_guess_is_ordered_by_free_parameters():
    config = RunConfig.from_dict(dict(
        MINIMAL, sampler={"initial_guess": {"k_PF": -2.2, "lambda_F": 6.5}}))
    fitter = config.build_fitter()
    assert fitter.free_param_names == ("lambda_F", "k_PF")
    assert config.initial_guess_for(fitter) == [6.5, -2.2]


def test_incomplete_initial_guess_is_rejected():
    config = RunConfig.from_dict(dict(
        MINIMAL, sampler={"initial_guess": {"lambda_F": 6.5}}))
    with pytest.raises(ValueError, match="missing: \\['k_PF'\\]"):
        config.initial_guess_for(config.build_fitter())


def test_unknown_initial_guess_keyword_is_rejected():
    with pytest.raises(ValueError, match="initial_guess must be a mapping"):
        RunConfig.from_dict(dict(MINIMAL,
                                 sampler={"initial_guess": "somewhere"}))


def test_to_dict_round_trips():
    config = RunConfig.from_dict(MINIMAL)
    assert RunConfig.from_dict(config.to_dict()).to_dict() == config.to_dict()


def test_sampler_config_is_replaceable():
    """`card fit --steps N` overrides by dataclasses.replace, so the sampler
    settings must stay a plain frozen dataclass."""
    import dataclasses

    sampler = dataclasses.replace(SamplerConfig(), n_steps=10)
    assert sampler.n_steps == 10 and sampler.n_walkers == 32


# ----------------------------------------------------------------------------
# The k_F / k_PF rename
#
# Both names are valid parameters, so a config written against the old meaning
# of k_F still parses.  These pin the guard that stops it being fitted silently.
# ----------------------------------------------------------------------------

def test_legacy_prior_on_k_F_is_rejected():
    """The dangerous case: k_F used to *be* the post-Flood constant."""
    legacy = dict(MINIMAL,
                  fixed={"lambda_c": 1.0, "k_c": 0.0, "t_c": 1.0,
                         "t_F": "flood_start_date"},
                  priors={"lambda_F": {"mean": 6.0, "sigma": 1.0},
                          "k_F": {"mean": -3.0, "sigma": 1.0}})
    with pytest.raises(ValueError, match="written before the two were split"):
        RunConfig.from_dict(legacy)


def test_legacy_nonzero_fixed_k_F_warns():
    legacy = dict(MINIMAL,
                  fixed={"lambda_c": 1.0, "k_c": 0.0, "k_F": 8.04e-3,
                         "t_c": 1.0, "t_F": "flood_start_date"},
                  priors={"lambda_F": {"mean": 6.0, "sigma": 1.0}})
    with pytest.warns(UserWarning, match="not after it"):
        RunConfig.from_dict(legacy)


def test_pinning_k_F_to_zero_is_the_new_idiom_and_is_silent(recwarn):
    """A constant-rate Flood is what the old model did, and says so clearly."""
    config = RunConfig.from_dict(dict(
        MINIMAL,
        fixed={"lambda_c": 1.0, "k_c": 0.0, "k_F": 0.0, "t_c": 1.0,
               "t_F": "flood_start_date"},
        priors={"lambda_F": {"mean": 6.0, "sigma": 1.0}}))
    assert config.fixed_params["k_F"] == 0.0
    assert [w for w in recwarn if "k_F" in str(w.message)] == []


def test_naming_k_PF_anywhere_takes_the_config_at_its_word(recwarn):
    config = RunConfig.from_dict(dict(
        MINIMAL,
        fixed={"lambda_c": 1.0, "k_c": 0.0, "k_F": 2.0, "t_c": 1.0,
               "t_F": "flood_start_date"},
        priors={"lambda_F": {"mean": 6.0, "sigma": 1.0},
                "k_PF": {"mean": -3.0, "sigma": 1.0}}))
    assert config.fixed_params["k_F"] == 2.0
    assert [w for w in recwarn if "k_F" in str(w.message)] == []


def test_t_F2_may_be_pinned_but_is_never_fitted():
    """The Flood's length is settable and structural: pinned, never free."""
    config = RunConfig.from_dict(dict(
        MINIMAL,
        fixed={"lambda_c": 1.0, "k_c": 0.0, "k_F": 0.0, "t_c": 1.0,
               "t_F": "flood_start_date", "t_F2": "flood_end_date"},
        priors={"lambda_F": {"mean": 6.0, "sigma": 1.0},
                "k_PF": {"mean": -3.0, "sigma": 1.0}}))
    fitter = config.build_fitter()
    assert config.fixed_params["t_F2"] == 1657.0
    assert "t_F2" not in fitter.free_param_names
    assert fitter.theta_to_params(np.array([6.0, -3.0])).t_F2 == 1657.0
