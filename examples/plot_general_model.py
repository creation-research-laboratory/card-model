"""
Schematic of the general model's decay-rate history, lambda(t).

Three relaxation constants are drawn on one axis to show how k controls the
return to the background rate after each accelerated period: a large k relaxes
within a few years of the event, a small one leaves the rate elevated for
thousands of years.

The x axis is a DATE — years after Day 1 of Creation — because that is the
timeline lambda is defined on.

This script used to re-implement the piecewise lambda(t) itself, with its own
Flood date and its own idea of the age of the Earth, so a change to the model
or to the chronology would not have reached the figure.  Both now come from the
package: `plot_lambda_history` evaluates `GeneralModel.lambda_func`, the same
function the solver integrates.

Writes general_model_plot.png to the current directory.
"""

import math

from card import (
    FLOOD_END_DATE,
    FLOOD_START_DATE,
    GeneralModelParams,
    plot_lambda_history,
)

# Peak rates, as multiples of the background rate.
LAMBDA_C = 1e3      # Creation week
LAMBDA_F = 1e5      # Flood

# One year of Flood, so the constant-rate region is visible on the figure.  The
# flood-only limit used elsewhere sets t_F2 == t_F, which has no width to draw.
FLOOD_END = max(FLOOD_END_DATE, FLOOD_START_DATE + 1)

# Relaxation constants, applied to both the post-Creation and post-Flood decay.
DECAY_CONSTANTS = [0.1, 0.01, 0.005]


def main():
    models = [
        GeneralModelParams(
            lambda_c=LAMBDA_C,
            lambda_F=LAMBDA_F,
            lambda_bg=1.0,
            k_c=k,
            k_F=k,
            t_c=1.0,
            t_F=FLOOD_START_DATE,
            t_F2=FLOOD_END,
        )
        for k in DECAY_CONSTANTS
    ]
    labels = [f"$k_c = k_F$ = {k:g}" for k in DECAY_CONSTANTS]

    out_file = plot_lambda_history(
        models, labels=labels, out_file='general_model_plot.png')

    print(f"Flood: DATE {FLOOD_START_DATE:g} to {FLOOD_END:g} "
          f"(years after Creation)")
    for k in DECAY_CONSTANTS:
        # How long the post-Flood rate stays 10x the background: the figure's
        # main message, as a number.
        years = math.log((LAMBDA_F - 1) / 9.0) / k
        print(f"  k = {k:<6g} rate is still 10x background "
              f"{years:,.0f} years after the Flood")
    print(f"\nSaved: {out_file}")


if __name__ == '__main__':
    main()
