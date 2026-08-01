"""
Fast end-to-end smoke test of the MCMC pipeline, via the `card` CLI.

`tests/test_inference.py` covers the fitter's pieces; this covers the whole
path a user actually runs — config file -> fitter -> chain -> HDF5 -> summary
-> figures — which is otherwise exercised only by `examples/run_card_mcmc.py`
at 32 walkers x 20000 steps, far too slow for CI.

The settings here (8 walkers, 60 steps, fixed seed) put the whole module at a
couple of seconds.  That is not enough sampling for a real posterior, so the
one statistical assertion is deliberately loose: the chain must land within a
factor of a few of the exact deterministic solution to the same constraints.
Anything tighter would be a flaky test of emcee, not of this package.
"""

import json
import os

import numpy as np
import pytest
import yaml

from card import load_results, solve_flood_only
from card.cli import main

SMOKE_CONFIG = {
    "chronology": {"age_of_earth": 6056.0, "flood_start_date": 1656.0,
                   "flood_end_date": 1656.0, "ice_age_end_date": 3500.0},
    "constraints": [
        {"young_age": "flood_start_age", "secular_age": 541.0e6,
         "uncertainty": 1.0e7, "label": "Precambrian-Cambrian boundary"},
        {"young_age": "ice_age_end_age", "secular_age": 11700.0,
         "uncertainty": 100.0, "label": "end of the Ice Age"},
    ],
    "fixed": {"lambda_c": 1.0, "k_c": 0.0, "t_c": 1.0,
              "t_F": "flood_start_date", "t_F2": "flood_end_date"},
    "priors": {"lambda_F": {"mean": 6.5, "sigma": 1.0},
               "k_F": {"mean": -2.2, "sigma": 1.0}},
    "sampler": {"n_walkers": 8, "n_steps": 60, "burn_in": 20, "seed": 4},
    "output": {"directory": "out", "figures": True},
}

FIT_ARGS = ("--walkers", "8", "--steps", "60", "--burn-in", "20", "--quiet")


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "smoke.yaml"
    path.write_text(yaml.safe_dump(SMOKE_CONFIG))
    return str(path)


def fit(config_path, out_dir, *extra):
    status = main(["fit", config_path, "-o", str(out_dir), *FIT_ARGS, *extra])
    assert status == 0
    return out_dir


# ----------------------------------------------------------------------------
# card fit
# ----------------------------------------------------------------------------

def test_fit_writes_the_whole_output_set(tmp_path, config_path):
    out = fit(config_path, tmp_path / "run")
    for name in ("chain.h5", "run_config.json", "summary_statistics.txt",
                 "corner_plot.png", "trace_plot.png",
                 "age_comparison_posterior.png"):
        assert os.path.getsize(out / name) > 0, f"{name} was not written"


def test_saved_chain_has_the_requested_shape(tmp_path, config_path):
    out = fit(config_path, tmp_path / "run")
    results = load_results(str(out / "chain.h5"))
    assert results["chain"].shape == (60, 8, 2)
    assert results["param_names"] == ["lambda_F", "k_F"]
    assert results["log_scale"] == [True, True]
    assert results["present_time"] == 6056.0
    assert 0.0 < results["acceptance_fraction"] < 1.0


def test_chain_lands_near_the_deterministic_solution(tmp_path, config_path):
    """The MCMC and `card.calibrate` answer the same two constraints, so a
    posterior that is not in the neighbourhood of the exact solve means the
    likelihood, the sampling space or the age conventions are wired up wrong —
    the class of bug this test exists to catch."""
    out = fit(config_path, tmp_path / "run")
    results = load_results(str(out / "chain.h5"))
    truth = solve_flood_only(flood_age=4400.0, flood_secular_age=541e6,
                             second_age=2556.0, second_secular_age=11700.0)

    median = np.median(results["samples"], axis=0)
    assert 10 ** median[0] == pytest.approx(truth.lambda_F, rel=2.0)
    assert 10 ** median[1] == pytest.approx(truth.k_F, rel=0.5)


def test_the_seed_makes_a_run_reproducible(tmp_path, config_path):
    """Without this, a CI failure here could never be reproduced locally."""
    first = load_results(str(fit(config_path, tmp_path / "a") / "chain.h5"))
    second = load_results(str(fit(config_path, tmp_path / "b") / "chain.h5"))
    np.testing.assert_array_equal(first["chain"], second["chain"])


def test_resolved_config_is_written_beside_the_chain(tmp_path, config_path):
    """With keywords resolved and CLI overrides folded in, this file is the
    only complete record of what was run."""
    out = fit(config_path, tmp_path / "run")
    with open(out / "run_config.json") as handle:
        resolved = json.load(handle)
    assert resolved["constraints"][0]["young_age"] == 4400.0   # was a keyword
    assert resolved["fixed"]["t_F"] == 1656.0                  # was a keyword
    assert resolved["sampler"]["n_steps"] == 60                # was 60 via CLI


def test_cli_overrides_beat_the_config(tmp_path, config_path):
    out = fit(config_path, tmp_path / "run", "--walkers", "10", "--steps",
              "30", "--seed", "7")
    assert load_results(str(out / "chain.h5"))["chain"].shape == (30, 10, 2)


def test_no_figures_skips_the_plots(tmp_path, config_path):
    """Matplotlib dominates the runtime of a short fit, so a headless run
    should be able to opt out of it."""
    out = fit(config_path, tmp_path / "run", "--no-figures")
    assert (out / "chain.h5").exists()
    assert not (out / "corner_plot.png").exists()
    assert (out / "summary_statistics.txt").exists()


def test_output_directory_is_created(tmp_path, config_path):
    out = fit(config_path, tmp_path / "nested" / "deeper")
    assert (out / "chain.h5").exists()


# ----------------------------------------------------------------------------
# card calibrate / schema / errors
# ----------------------------------------------------------------------------

def test_calibrate_solves_the_same_config(capsys, config_path):
    assert main(["calibrate", config_path]) == 0
    printed = capsys.readouterr().out
    truth = solve_flood_only(flood_age=4400.0, flood_secular_age=541e6,
                             second_age=2556.0, second_secular_age=11700.0)
    assert f"{truth.lambda_F:.6g}" in printed
    assert "Precambrian-Cambrian boundary" in printed


def test_calibrate_needs_exactly_two_constraints(capsys, tmp_path):
    single = dict(SMOKE_CONFIG,
                  constraints=SMOKE_CONFIG["constraints"][:1])
    path = tmp_path / "one.yaml"
    path.write_text(yaml.safe_dump(single))
    assert main(["calibrate", str(path)]) == 2
    assert "exactly two" in capsys.readouterr().err


def test_schema_prints_the_parameter_spec(capsys):
    assert main(["schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["properties"]["lambda_F"]["x-log-scale"] is True


def test_schema_chronology_prints_the_defaults(capsys):
    assert main(["schema", "--chronology"]) == 0
    assert json.loads(capsys.readouterr().out)["age_of_earth"] == 6056.0


def test_a_bad_config_exits_nonzero_without_a_traceback(capsys, tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(dict(SMOKE_CONFIG, smapler={})))
    assert main(["fit", str(path), "-o", str(tmp_path / "out")]) == 2
    assert "unrecognized key" in capsys.readouterr().err


def test_a_missing_config_exits_nonzero(capsys, tmp_path):
    assert main(["fit", str(tmp_path / "absent.yaml")]) == 2
    assert "No run config" in capsys.readouterr().err
