# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CARD ("Calibrating Accelerated Radiometric Decay", formerly RIAG) is a research project modeling time-varying (accelerated) radiometric decay rates within a young-earth creation framework. It converts between "true" young-earth ages and apparent "secular" ages under a piecewise decay-rate model, and fits model parameters to age constraints via MCMC.

`RIAG_model.qmd` is the Quarto write-up (math derivations + self-contained embedded Python — it does not import the package); the `card` package does the real numerics. The repo is a git repository (GitHub-bound) but still lives in a Dropbox folder synced across machines. It is mid-restructure — see `repo_todo.md` for the phased plan and current status.

## Layout

- `src/card/` — the installable package (`pip install -e .` → `import card`): `decay_solver.py` (models), `card_mcmc.py` (MCMC fitting), `create_custom_plots.py` (MCMC output plots). Public API re-exported in `__init__.py`.
- `tests/` — pytest suite.
- Repo root — driver/figure scripts (`run_card_mcmc.py`, `plot_model_calibration*.py`, `demo_parameter_sweep.py`, `plot_general_model.py`); these become `examples/` in Phase 3.

## Environment and Commands

- Python venv at `.venv/`, but it was created on another machine (Dropbox-synced) and its interpreter symlinks may be broken on the current one. If `.venv/bin/python` fails, create a venv **outside Dropbox** (e.g. in the session scratchpad) rather than recreating `.venv` in place, which would break it on the other machine: `python3 -m venv <path> && <path>/bin/pip install -e ".[dev]"` (deps declared in `pyproject.toml`; add `jupyter` for Quarto rendering).
- The root scripts and tests import the `card` package, so the package must be installed (editable install above) — there is no sys.path hack.
- Run the unit tests: `python -m pytest` (config in `pyproject.toml`).
  Note: `python src/card/decay_solver.py` does NOT run tests — its `__main__` block generates parameter-sweep example plots.
- Run the main MCMC inversion (writes to `mcmc_output/`): `python run_card_mcmc.py`
- Render the paper: `quarto render RIAG_model.qmd` (produces HTML and PDF)

## Time and Normalization Conventions (critical)

- Two time conventions coexist: **years after Day 1 of Creation** (forward time `t`) and **years before present** (YBP, `tau`). `decay_solver.py` internals use years-after-Creation; the `forward_age`/`inverse_age` API and MCMC data use YBP. Conversion helpers `years_before_present_to_years_after_creation` / `..._to_years_before_present` exist in decay_solver.py.
- All decay rates are normalized to the background rate: `lambda_bg = 1.0` always.
- Key constants in decay_solver.py: `AGE_OF_EARTH = 6056` (years after Creation), `FLOOD_START = FLOOD_END = 1656` (years after Creation) with `FLOOD_AGE = 4400` (YBP), `ICE_AGE_END_AGE = 3500` (years after Creation) with `ICE_AGE_END_YBP = 2556` (YBP). The `_AGE` suffix means years-after-Creation; `_YBP`/`FLOOD_AGE` are years-before-present — pass the YBP values as MCMC young ages. (Resolved 2026-07-19; MCMC results generated before then used 3500 as YBP and are stale.)

## Architecture

- **src/card/decay_solver.py** — core module. `DecayModel` abstract base with `ConstantDecayModel` (analytic) and `GeneralModel` (numeric integration via scipy `quad`/`fsolve`). The flood-only limit is built via `GeneralModel.flood_only(lambda_F, k_F, t_F=...)` (the old standalone `FloodOnlyModel`, whose post-Flood exponential was anchored at the present, was removed 2026-07-19). Each model supports `forward_age` (true young-earth age → apparent secular age) and `inverse_age` (numerical inverse). Parameters travel in the `GeneralModelParams` dataclass. Plotting utilities (`plot_age_comparison`, `plot_general_model_parameter_sweep`) live here pending the Phase 2 split.
  - Known numerical issue: `GeneralModel.compute_integral` calls `quad` without breakpoints, so integrals spanning the discontinuous Flood spike carry up to ~5e-4 relative error (fix: pass `points=[t_F, t_F2]`; tracked in repo_todo.md; the tolerance in tests/test_characterization.py documents it).
- **tests/** — `test_models.py` (round-trip, boundary, domain-validation tests) and `test_characterization.py` (pins known-good numbers from 2026-07-19, including the todo.md calibration solutions; if a deliberate model change shifts them, re-pin in the same commit).
- **src/card/card_mcmc.py** — `CARDMCMC` class: Bayesian fitting of `GeneralModel` parameters with emcee. Samples in **log10 space** (`theta_to_params` applies `10**theta`; prior means/sigmas are log10 values). Any of the 7 parameters can be pinned via `fixed_params`, which is how reduced models are fit.
- **run_card_mcmc.py** — the main driver. Fits the flood-only limit of the General model (fixes `lambda_c`, `k_c`, `t_c`, `t_F`, `t_F2`; frees `lambda_F`, `k_F`) against two constraints: Flood-age rocks (4400 YBP) appear 540 Myr old, Ice-Age-end rocks (2556 YBP) appear 11.5 kyr old. Chains post-processing from create_custom_plots.py and writes everything to `mcmc_output/`.
- **src/card/create_custom_plots.py** — loads saved MCMC output from text files (`samples.txt`, `log_probs.txt`, `param_names.txt`) and produces styled corner/trace plots and `summary_statistics.txt`.
- **plot_model_calibration.py**, **plot_model_calibration_joint.py** — flood-only calibration scenarios (fixed-`k_F` and joint solve); their solved values are pinned in the characterization tests.
- **demo_parameter_sweep.py**, **plot_general_model.py** — standalone plot generators for the paper figures.
