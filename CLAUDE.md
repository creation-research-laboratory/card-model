# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CARD ("Calibrating Accelerated Radiometric Decay", formerly RIAG) is a research project modeling time-varying (accelerated) radiometric decay rates within a young-earth creation framework. It converts between "true" young-earth ages and apparent "secular" ages under a piecewise decay-rate model, and fits model parameters to age constraints via MCMC.

`docs/paper/CARD_model.qmd` is the Quarto write-up (math derivations + self-contained embedded Python — it does not import the package); the `card` package does the real numerics. The restructuring plan and status live in `repo_todo.md`, which is **gitignored** (local planning file, as are `todo.md`/`notes.md`) — they exist only in the original working copy, not in fresh clones.

## Layout

- `src/card/` — the installable package (`pip install -e .` → `import card`): `decay_solver.py` (models), `card_mcmc.py` (MCMC fitting), `create_custom_plots.py` (MCMC output plots). Public API re-exported in `__init__.py`.
- `tests/` — pytest suite.
- `examples/` — driver/figure scripts (`run_card_mcmc.py`, `plot_model_calibration*.py`, `demo_parameter_sweep.py`, `plot_general_model.py`); they import the installed `card` package and write outputs (PNGs, `mcmc_output/`) to the current working directory.
- `docs/paper/` — the Quarto paper.

## Environment and Commands

- Setup: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"` (deps declared in `pyproject.toml`; add `jupyter` for Quarto rendering). Caution: if this checkout is still inside a Dropbox-synced folder, do NOT create or recreate `.venv` in place (its interpreter symlinks sync across machines and break) — use a venv outside the synced tree instead. In a normal per-machine git clone, an in-repo `.venv` is fine.
- The root scripts and tests import the `card` package, so the package must be installed (editable install above) — there is no sys.path hack.
- Run the unit tests: `python -m pytest` (config in `pyproject.toml`).
  Note: `python src/card/decay_solver.py` does NOT run tests — its `__main__` block generates parameter-sweep example plots.
- Run the main MCMC inversion (writes to `mcmc_output/`): `python examples/run_card_mcmc.py`
- Render the paper: `quarto render docs/paper/CARD_model.qmd` (produces HTML and PDF; render artifacts are gitignored)

## Time and Normalization Conventions (critical)

- Two time conventions coexist, and **the name of a quantity says which one it uses** (rule established 2026-07-26, documented in `chronology.py`):
  - **`*_DATE`** — years after Day 1 of Creation (forward time `t`). Model parameters `t_c`/`t_F`/`t_F2` and `lambda_func(t)` are DATEs.
  - **`*_AGE`** — years before present (YBP, `tau`). Everything into or out of `forward_age`/`inverse_age`, and all `CARDMCMC` data ages, are AGEs.
  - A DATE and its matching AGE sum to `AGE_OF_EARTH`; `tests/test_chronology.py` pins these relationships so a refactor cannot silently flip one.
- Chronology values are **user-specifiable modeling assumptions, not constants**: the frozen `Chronology` dataclass in `chronology.py` holds `age_of_earth` (6056), `flood_start_date`/`flood_end_date` (1656), `ice_age_end_date` (3500), derives the matching AGEs as properties, and loads/saves JSON config files. `DEFAULT_CHRONOLOGY` backs the convenience constants re-exported from decay_solver.py (`AGE_OF_EARTH`, `FLOOD_START_DATE`, `FLOOD_END_DATE`, `FLOOD_AGE` = 4400, `ICE_AGE_END_DATE` = 3500, `ICE_AGE_END_AGE` = 2556). MCMC results generated before 2026-07-19 fit the Ice Age at 3500 YBP instead of 2556 and are stale.
- Removed 2026-07-26: `FLOOD_START`/`FLOOD_END` (now `*_DATE`), `ICE_AGE_END_YBP` (now `ICE_AGE_END_AGE`), and `PC_CAMBRIAN_BOUNDARY` (was labeled years-after-Creation but the paper used 5400 as YBP; it matched neither current constant and had no callers). Note `ICE_AGE_END_AGE` **kept its name but changed meaning** — it is now 2556 (YBP), not 3500.
- `GeneralModelParams` validates on construction: all lambdas >= 1 (rates are multiples of background), `k_c`/`k_F` >= 0 (the minus sign is already in `exp(-k*dt)`, so positive k is what decays; k=0 is the no-relaxation limit), dates ordered `t_c <= t_F <= t_F2` (equality of the last pair is the instantaneous-Flood limit), and a warning when the Flood exceeds `MAX_UNREMARKED_FLOOD_DURATION` (2 years) or when `lambda_bg != 1` (which is normalized to 1 rather than rejected). `CARDMCMC.log_likelihood` catches `ValueError` specifically, which is how these bounds reach the sampler — do not widen it back to `except Exception`.

## Architecture

- **src/card/decay_solver.py** — core module. `DecayModel` abstract base with `ConstantDecayModel` (analytic) and `GeneralModel` (numeric integration via scipy `quad`/`fsolve`). The flood-only limit is built via `GeneralModel.flood_only(lambda_F, k_F, t_F=...)` (the old standalone `FloodOnlyModel`, whose post-Flood exponential was anchored at the present, was removed 2026-07-19). Each model supports `forward_age` (true young-earth age → apparent secular age) and `inverse_age` (numerical inverse). Parameters travel in the `GeneralModelParams` dataclass. Plotting utilities (`plot_age_comparison`, `plot_general_model_parameter_sweep`) live here pending the Phase 2 split.
  - `GeneralModel.compute_integral` evaluates the piecewise integral in **closed form** (every region is constant or a decaying exponential) rather than by quadrature, and `inverse_age` uses a bracketed `brentq` solve on `[0, present_time]`. Both replaced numerical approximations on 2026-07-26: `quad` without breakpoints misplaced up to 0.8% of integrals spanning the Flood discontinuity and made `forward_age` non-monotone, which in turn made the old `fsolve` inverse fail on up to 17% of targets. Do not reintroduce quadrature here; if a future model has no closed form, give the base class a `quad` fallback that is passed the model's breakpoints.
- **tests/** — `test_models.py` (round-trip, boundary, domain-validation tests) and `test_characterization.py` (pins known-good numbers from 2026-07-19, including the todo.md calibration solutions; if a deliberate model change shifts them, re-pin in the same commit).
- **src/card/card_mcmc.py** — `CARDMCMC` class: Bayesian fitting of `GeneralModel` parameters with emcee. Samples in **log10 space** (`theta_to_params` applies `10**theta`; prior means/sigmas are log10 values). Any of the 7 parameters can be pinned via `fixed_params`, which is how reduced models are fit.
- **examples/run_card_mcmc.py** — the main driver. Fits the flood-only limit of the General model (fixes `lambda_c`, `k_c`, `t_c`, `t_F`, `t_F2`; frees `lambda_F`, `k_F`) against two constraints: Flood-age rocks (4400 YBP) appear 540 Myr old, Ice-Age-end rocks (2556 YBP) appear 11.5 kyr old. Chains post-processing from create_custom_plots.py and writes everything to `mcmc_output/`.
- **src/card/create_custom_plots.py** — loads saved MCMC output from text files (`samples.txt`, `log_probs.txt`, `param_names.txt`) and produces styled corner/trace plots and `summary_statistics.txt`.
- **examples/plot_model_calibration.py**, **examples/plot_model_calibration_joint.py** — flood-only calibration scenarios (fixed-`k_F` and joint solve); their solved values are pinned in the characterization tests. The joint script imports from the fixed-`k_F` one, so run them from `examples/`.
- **examples/demo_parameter_sweep.py**, **examples/plot_general_model.py** — standalone plot generators for the paper figures (plot_general_model.py hand-rolls its own λ(t) rather than using the package — rewrite pending, see repo_todo.md).
