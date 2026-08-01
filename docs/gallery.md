# Figure gallery

Every figure below is produced by a script in `examples/`, and every one of
them draws through the package rather than re-implementing the model. They are
regenerated each time this site is built, so what you see is what the current
code produces.

To reproduce them all locally:

```bash
python examples/plot_general_model.py
python examples/plot_model_calibration.py
python examples/plot_model_calibration_joint.py
python examples/demo_parameter_sweep.py
```

Each writes its PNG to the current directory.

## The decay rate through time

`examples/plot_general_model.py` — the full model's \(\lambda(t)\) for three
relaxation constants, showing how \(k\) controls the return to the background
rate after each accelerated period. The x axis is a DATE.

![Decay rate through time](img/general_model_plot.png){ loading=lazy }

Drawn by [`plot_lambda_history`](api/plotting.md), which the paper's schematic
figure also calls — so the figure and the function the solver integrates cannot
drift apart.

## Calibration against two dated events

`examples/plot_model_calibration.py` — two scenarios, each pinning the Flood to
541 Ma with \(k_F\) fixed, solving for \(\lambda_F\). The Ice Age point is then
a *check*, and it misses by ~18%, which is the useful part: one constraint
cannot honor two dates.

![Calibration with k_F fixed](img/model_calibration_plot.png){ loading=lazy }

`examples/plot_model_calibration_joint.py` — the same two scenarios solving for
**both** \(\lambda_F\) and \(k_F\). Two equations, two unknowns, so both
calibration points land exactly on the curve.

![Joint calibration](img/model_calibration_joint_plot.png){ loading=lazy }

## Parameter sweeps

`examples/demo_parameter_sweep.py` — secular age against young age as
parameters vary, via
[`plot_general_model_parameter_sweep`](api/plotting.md).

![Sweep over lambda_F and k_F](img/demo_sweep_lambdaF_kF.png){ loading=lazy }

![Sweep over lambda_F alone](img/demo_sweep_lambdaF_only.png){ loading=lazy }

![Sweep over the decay constants](img/demo_sweep_decay_constants.png){ loading=lazy }

## MCMC output

`card fit examples/flood_only.yaml` writes a corner plot, trace plots and an
age-comparison figure alongside the chain. They are not reproduced here because
they take a few seconds of sampling to generate; see
[tutorial 2](tutorials/fitting.md) for what they show and how to read them.
