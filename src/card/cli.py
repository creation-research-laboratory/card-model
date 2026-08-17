"""
Command-line entry point: ``card <command> ...``.

Four commands, all of which are thin wrappers over the package API:

    card init myrun.yaml        write a starter run config to edit
    card fit myrun.yaml         run the MCMC a config file describes
    card calibrate myrun.yaml   solve the same constraints deterministically
    card schema                 print the parameter/chronology JSON schema

``card fit`` is the config-driven form of `examples/run_card_mcmc.py`: it
writes ``chain.h5``, the corner/trace/age-comparison figures and
``summary_statistics.txt`` into the config's output directory.  ``card
calibrate`` needs no sampler at all — with the flood-only limit pinned and as
many matched date pairs as there are unknown rates (two for ``lambda_F`` and
``k_PF``, three to add ``k_F``), the answer is an exact root solve (see
`card.calibrate`), so it is the right command when the constraints are exact
and the uncertainties are only there to satisfy the config schema.

Everything heavy (numpy, emcee, matplotlib) is imported inside the command that
needs it, so ``card --help`` and ``card schema`` stay fast.
"""

import argparse
import json
import os
import sys
from typing import Optional, Sequence

from . import __version__
from .config import RunConfig

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="card",
        description="Calibrating Accelerated Radiometric Decay (CARD).",
    )
    parser.add_argument("--version", action="version",
                        version=f"card {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser(
        "init", help="write a documented starter run config")
    init.add_argument("path", nargs="?", default="card_run.yaml",
                      help="where to write it (default: card_run.yaml)")
    init.add_argument("-f", "--force", action="store_true",
                      help="overwrite the file if it already exists")

    fit = subparsers.add_parser(
        "fit", help="run the MCMC fit described by a YAML/JSON config")
    fit.add_argument("config", help="path to a .yaml, .yml or .json run config")
    fit.add_argument("-o", "--output", default=None,
                     help="output directory (overrides output.directory)")
    fit.add_argument("--walkers", type=int, default=None,
                     help="number of walkers (overrides sampler.n_walkers)")
    fit.add_argument("--steps", type=int, default=None,
                     help="production steps (overrides sampler.n_steps)")
    fit.add_argument("--burn-in", type=int, default=None, dest="burn_in",
                     help="burn-in steps (overrides sampler.burn_in)")
    fit.add_argument("--seed", type=int, default=None,
                     help="random seed (overrides sampler.seed)")
    fit.add_argument("--no-figures", action="store_true",
                     help="write the chain and summary but skip the figures")
    fit.add_argument("-q", "--quiet", action="store_true",
                     help="suppress the progress bar and the summary print-out")

    calibrate = subparsers.add_parser(
        "calibrate",
        help="solve a two-constraint config exactly, without sampling")
    calibrate.add_argument("config", help="path to a run config")

    schema = subparsers.add_parser(
        "schema", help="print the model parameter spec as JSON Schema")
    schema.add_argument("--chronology", action="store_true",
                        help="print the default chronology instead")

    return parser


# -------------------------------------------------------------------- init
def _run_init(args) -> int:
    from .config import example_config_text

    if os.path.exists(args.path) and not args.force:
        raise ValueError(
            f"{args.path!r} already exists.  Pass --force to overwrite it, or "
            "choose another path."
        )

    directory = os.path.dirname(args.path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(args.path, "w") as handle:
        handle.write(example_config_text())

    print(f"Wrote {args.path}")
    print(f"Edit it, then run:  card fit {args.path}")
    print(f"Or, for the exact solve:  card calibrate {args.path}")
    return 0


# --------------------------------------------------------------------- fit
def _apply_overrides(config: RunConfig, args) -> RunConfig:
    """Apply the command-line overrides to a loaded config."""
    import dataclasses

    sampler_overrides = {
        name: getattr(args, name)
        for name in ("n_walkers", "n_steps", "burn_in", "seed")
        if getattr(args, name, None) is not None
    }
    if args.quiet:
        sampler_overrides["progress"] = False
    sampler = (dataclasses.replace(config.sampler, **sampler_overrides)
               if sampler_overrides else config.sampler)

    return dataclasses.replace(
        config,
        sampler=sampler,
        output_dir=args.output or config.output_dir,
        figures=config.figures and not args.no_figures,
    )


def _run_fit(args) -> int:
    from .plotting import (
        plot_age_comparison,
        plot_mcmc_corner,
        plot_mcmc_traces,
        summarize_mcmc,
    )

    # argparse names the flags --walkers/--steps; the config calls them
    # n_walkers/n_steps.  Bridge here so _apply_overrides can stay generic.
    args.n_walkers, args.n_steps = args.walkers, args.steps

    config = _apply_overrides(RunConfig.from_file(args.config), args)
    out_dir = config.output_dir
    os.makedirs(out_dir, exist_ok=True)

    fitter = config.build_fitter()
    initial_guess = config.initial_guess_for(fitter)
    if not args.quiet:
        print(f"Fitting {len(config.constraints)} constraint(s) for "
              f"{', '.join(fitter.free_param_names)} "
              f"({config.sampler.n_walkers} walkers x "
              f"{config.sampler.n_steps} steps)")
        if initial_guess is not None:
            print("starting the walkers at "
                  + ", ".join(f"{name}={value:.6g}" for name, value
                              in zip(fitter.free_param_names, initial_guess))
                  + " (sampling space)")

    results = fitter.run_mcmc(
        n_walkers=config.sampler.n_walkers,
        n_steps=config.sampler.n_steps,
        burn_in=config.sampler.burn_in,
        initial_guess=initial_guess,
        init_spread=config.sampler.init_spread,
        progress=config.sampler.progress and not args.quiet,
        # The seed goes to the fitter's own Generator rather than to
        # np.random.seed, so a run is reproducible without reaching into
        # process-global state that other code may also be using.
        seed=config.sampler.seed,
    )

    written = [fitter.save_results(results, os.path.join(out_dir, "chain.h5"))]
    # Keep the resolved config beside the chain: with keywords and CLI
    # overrides folded in, this is the only complete record of what was run.
    resolved_path = os.path.join(out_dir, "run_config.json")
    with open(resolved_path, "w") as handle:
        json.dump(config.to_dict(), handle, indent=2)
        handle.write("\n")
    written.append(resolved_path)

    param_names, log_scale = results["param_names"], results["log_scale"]
    summary = summarize_mcmc(
        results["samples"], param_names, log_scale=log_scale,
        out_file=os.path.join(out_dir, "summary_statistics.txt"))
    written.append(os.path.join(out_dir, "summary_statistics.txt"))

    if config.figures:
        written.append(plot_mcmc_corner(
            results["samples"], param_names,
            prior_means=config.prior_means or None,
            prior_sigmas=config.prior_sigmas or None,
            log_scale=log_scale,
            out_file=os.path.join(out_dir, "corner_plot.png")))
        written.append(plot_mcmc_traces(
            results["chain"], results["log_prob_chain"], param_names,
            log_scale=log_scale,
            out_file=os.path.join(out_dir, "trace_plot.png")))

        stats = {row["parameter"]: row for row in summary}
        if {"lambda_F", "k_PF"} <= set(stats):
            # The age-comparison figure is a flood-only picture, so it is only
            # drawn when those are the parameters that were actually sampled.
            # Note the linear_ keys: both are sampled in log10.
            written.append(plot_age_comparison(
                age_of_earth=config.chronology.age_of_earth,
                lambda_F=stats["lambda_F"]["linear_mean"],
                k_PF=stats["k_PF"]["linear_mean"],
                lambda_F_median=stats["lambda_F"]["linear_median"],
                k_PF_median=stats["k_PF"]["linear_median"],
                flood_date=config.chronology.flood_start_date,
                out_file=os.path.join(out_dir, "age_comparison_posterior.png")))

    if not args.quiet:
        print(f"\nmean acceptance fraction: {results['acceptance_fraction']:.3f}")
        print(f"autocorrelation time:     {results['autocorr_time']}")
        stuck = results.get('stuck_walkers', [])
        if len(stuck):
            # run_mcmc has already warned; repeat it where the numbers are
            # printed, because the numbers themselves are what it invalidates.
            print(f"WARNING: {len(stuck)} walker(s) never joined the ensemble "
                  f"{list(stuck)}; the percentiles below are contaminated.  "
                  "Set sampler.initial_guess (try `calibrate`) and re-run.")
        for row in summary:
            print(f"{row['parameter']}: {row['linear_median']:.6g} "
                  f"[{row['linear_16%']:.6g}, {row['linear_84%']:.6g}]")
        print("\nWrote:")
        for path in written:
            print(f"  {path}")
    return 0


# --------------------------------------------------------------- calibrate
def _run_calibrate(args) -> int:
    config = RunConfig.from_file(args.config)
    ordered = sorted(config.constraints,
                     key=lambda c: c.young_age, reverse=True)
    # Two pairs solve for lambda_F and k_PF; three solve for k_F as well.  The
    # dispatch and its checks live on RunConfig, so `card calibrate` and
    # `sampler.initial_guess: calibrate` cannot solve different problems from
    # the same file.
    result = config.solve_exactly()
    solved_k_F = len(ordered) == 3

    print(f"lambda_F = {result.lambda_F:.6g}  (x background)")
    print(f"k_PF     = {result.k_PF:.6g}  /year")
    if solved_k_F:
        print(f"k_F      = {result.k_F:.6g}  /year  (solved; three pairs "
              "determine all three rates)")
    else:
        print(f"k_F      = {result.k_F:.6g}  /year  (held fixed; two pairs "
              "cannot determine three rates)")
    print(f"lambda_F2 = {result.lambda_F2:.6g}  (x background, at the Flood's end)")
    print(f"Flood placed at DATE {result.flood_date:g} "
          f"(AGE {ordered[0].young_age:g} YBP)")
    for constraint, residual in zip(ordered, result.residuals):
        label = constraint.label or f"{constraint.young_age:g} YBP"
        print(f"  {label}: target {constraint.secular_age:.6g} yr, "
              f"relative residual {residual:+.1e}")
    return 0


# ------------------------------------------------------------------ schema
def _run_schema(args) -> int:
    if args.chronology:
        from .chronology import DEFAULT_CHRONOLOGY

        print(json.dumps(DEFAULT_CHRONOLOGY.to_dict(), indent=2))
        return 0

    from .models import GeneralModelParams
    from .parameters import to_json_schema

    print(json.dumps(to_json_schema(GeneralModelParams), indent=2))
    return 0


_COMMANDS = {
    "init": _run_init,
    "fit": _run_fit,
    "calibrate": _run_calibrate,
    "schema": _run_schema,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    Run the CLI.

    Args:
        argv: Argument list, defaulting to `sys.argv[1:]`.

    Returns:
        Process exit status: 0 on success, 2 when the config is missing or
        invalid.
    """
    args = _build_parser().parse_args(list(argv) if argv is not None
                                      else None)
    try:
        return _COMMANDS[args.command](args)
    except (ValueError, FileNotFoundError) as error:
        # Config problems are user errors, not tracebacks: the message already
        # names the offending key.
        print(f"card {args.command}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
