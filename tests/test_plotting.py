"""
Tests for figure generation.

These check the things that can silently go wrong in plotting code and would
otherwise only be caught by a human looking at a PNG: unit mix-ups in the
summary statistics, a library stomping on the host's matplotlib backend, and
the chain-reshaping that used to be guesswork.
"""

import matplotlib
import numpy as np
import pytest

from card import (
    FLOOD_START_DATE,
    GeneralModel,
    GeneralModelParams,
    plot_age_comparison,
    plot_general_model_parameter_sweep,
    plot_lambda_history,
    plot_mcmc_corner,
    plot_mcmc_traces,
    summarize_mcmc,
)


@pytest.fixture
def fake_chain():
    """A small deterministic chain: (steps, walkers, params)."""
    rng = np.random.default_rng(0)
    chain = np.stack([
        rng.normal(6.5, 0.05, size=(40, 6)),   # log10 lambda_F
        rng.normal(-2.2, 0.03, size=(40, 6)),  # log10 k_F
    ], axis=-1)
    log_prob = rng.normal(-5, 1, size=(40, 6))
    return chain, log_prob, ['lambda_F', 'k_F']


# ----------------------------------------------------------------------------
# Backend hygiene
# ----------------------------------------------------------------------------

def test_plotting_does_not_change_the_matplotlib_backend(tmp_path):
    """A library must never call matplotlib.use().  An earlier version forced
    "Agg" at call time, which overrode a host GUI's backend process-wide and
    silently turned show=True into a no-op."""
    before = matplotlib.get_backend()
    plot_age_comparison(n_points=20, out_file=str(tmp_path / "a.png"))
    assert matplotlib.get_backend() == before


def test_plotting_into_a_supplied_axes_leaves_the_figure_to_the_caller(tmp_path):
    """The `ax` path is what a GUI uses: nothing is saved, shown or closed."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    returned = plot_age_comparison(n_points=20, ax=ax,
                                   out_file=str(tmp_path / "unused.png"))
    assert returned is ax
    assert not (tmp_path / "unused.png").exists()
    assert ax.get_xlabel() == "Young age (years before present)"
    plt.close(fig)


# ----------------------------------------------------------------------------
# Age-curve figures
# ----------------------------------------------------------------------------

def test_age_comparison_writes_a_file(tmp_path):
    out = tmp_path / "age.png"
    assert plot_age_comparison(n_points=50, out_file=str(out)) == str(out)
    assert out.stat().st_size > 0


def test_parameter_sweep_writes_a_file(tmp_path):
    out = tmp_path / "sweep.png"
    result = plot_general_model_parameter_sweep(
        vary_params={'lambda_F': [1e5, 1e6]}, n_points=50, out_file=str(out))
    assert result == str(out)
    assert out.stat().st_size > 0


def test_lambda_history_writes_a_file(tmp_path):
    out = tmp_path / "lambda.png"
    result = plot_lambda_history(
        GeneralModel.flood_only(lambda_F=1e5, k_F=1e-2), n_points=50,
        out_file=str(out))
    assert result == str(out)
    assert out.stat().st_size > 0


def test_lambda_history_draws_the_model_not_a_copy_of_it(tmp_path):
    """The curve must come from `lambda_func` itself — the failure this figure
    used to have was a hand-rolled piecewise function drifting from the model."""
    import matplotlib.pyplot as plt

    model = GeneralModel(GeneralModelParams.defaults(
        lambda_c=1e3, lambda_F=1e5, k_c=1e-1, k_F=1e-2,
        t_F=FLOOD_START_DATE, t_F2=FLOOD_START_DATE + 1))
    fig, ax = plt.subplots()
    plot_lambda_history(model, n_points=200, ax=ax)

    x, y = ax.get_lines()[0].get_data()
    for value, drawn in zip(x[::20], y[::20]):
        assert drawn == pytest.approx(model.lambda_func(value))
    plt.close(fig)


def test_lambda_history_accepts_params_and_several_models(tmp_path):
    out = tmp_path / "many.png"
    models = [GeneralModelParams.defaults(k_F=k) for k in (1e-2, 1e-3)]
    plot_lambda_history(models, labels=["fast", "slow"], n_points=50,
                        out_file=str(out))
    assert out.stat().st_size > 0


def test_lambda_history_x_axis_is_a_date(tmp_path):
    """The age-curve figures plot AGEs; this one plots DATEs, and mixing the
    two up is the mistake the naming rule exists to prevent."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    plot_lambda_history(GeneralModel.flood_only(lambda_F=1e5, k_F=1e-2),
                        n_points=20, ax=ax)
    assert ax.get_xlabel() == "Time (years after Creation)"
    plt.close(fig)


def test_lambda_history_rejects_mismatched_labels(tmp_path):
    with pytest.raises(ValueError, match="labels has 1 entries"):
        plot_lambda_history([GeneralModelParams.defaults(),
                             GeneralModelParams.defaults(k_F=1e-3)],
                            labels=["only one"], n_points=10,
                            out_file=str(tmp_path / "x.png"))


def test_sweep_rejects_unknown_parameter_names(tmp_path):
    with pytest.raises(ValueError, match="unknown parameters"):
        plot_general_model_parameter_sweep(
            vary_params={'lambda_typo': [1.0]}, n_points=10,
            out_file=str(tmp_path / "x.png"))


# ----------------------------------------------------------------------------
# Summary statistics — the unit trap
# ----------------------------------------------------------------------------

def test_summary_reports_both_sampling_and_linear_units():
    """lambda_F is sampled in log10, so `median` is ~6.5 while the model wants
    ~3.2e6.  Reporting only the former is what made the driver plot a
    lambda_F of 6.5; both must be available and clearly named."""
    samples = np.column_stack([
        np.full(100, 6.5),    # log10 lambda_F
        np.full(100, -2.2),   # log10 k_F
    ])
    rows = summarize_mcmc(samples, ['lambda_F', 'k_F'])
    by_name = {row['parameter']: row for row in rows}

    assert by_name['lambda_F']['median'] == pytest.approx(6.5)
    assert by_name['lambda_F']['linear_median'] == pytest.approx(10 ** 6.5)
    assert by_name['k_F']['linear_median'] == pytest.approx(10 ** -2.2)
    assert by_name['lambda_F']['log_scale'] is True


def test_summary_leaves_linear_parameters_alone():
    """A linear-scale parameter must not be exponentiated."""
    samples = np.full((50, 1), 1656.0)
    row = summarize_mcmc(samples, ['t_F'])[0]
    assert row['log_scale'] is False
    assert row['median'] == pytest.approx(1656.0)
    assert row['linear_median'] == pytest.approx(1656.0)


def test_summary_scale_flags_default_to_the_model_spec():
    samples = np.column_stack([np.full(20, 6.0), np.full(20, 1656.0)])
    rows = summarize_mcmc(samples, ['lambda_F', 't_F'])
    assert [row['log_scale'] for row in rows] == [True, False]


def test_summary_writes_a_report(tmp_path):
    out = tmp_path / "summary.txt"
    samples = np.column_stack([np.linspace(6.0, 7.0, 50)])
    summarize_mcmc(samples, ['lambda_F'], out_file=str(out))
    text = out.read_text()
    assert "lambda_F" in text and "log10" in text and "linear" in text


# ----------------------------------------------------------------------------
# Chain figures
# ----------------------------------------------------------------------------

def test_corner_plot_writes_a_file(tmp_path, fake_chain):
    chain, _, names = fake_chain
    out = tmp_path / "corner.png"
    plot_mcmc_corner(chain.reshape(-1, 2), names,
                     prior_means={'lambda_F': 6.5, 'k_F': -2.2},
                     prior_sigmas={'lambda_F': 1.0, 'k_F': 1.0},
                     out_file=str(out))
    assert out.stat().st_size > 0


def test_trace_plot_uses_the_structured_chain(tmp_path, fake_chain):
    """The chain arrives shaped (steps, walkers, params) from the fitter, so
    nothing has to reconstruct the walker count."""
    chain, log_prob, names = fake_chain
    out = tmp_path / "trace.png"
    plot_mcmc_traces(chain, log_prob, names, out_file=str(out))
    assert out.stat().st_size > 0


def test_trace_plot_rejects_a_flattened_chain(tmp_path, fake_chain):
    chain, log_prob, names = fake_chain
    with pytest.raises(ValueError, match="shape \\(steps, walkers, params\\)"):
        plot_mcmc_traces(chain.reshape(-1, 2), log_prob, names,
                         out_file=str(tmp_path / "t.png"))


def test_trace_plot_caps_the_walkers_it_draws(tmp_path):
    """Many walkers must not produce an unreadable figure."""
    rng = np.random.default_rng(1)
    chain = rng.normal(0, 1, size=(10, 40, 1))
    log_prob = rng.normal(0, 1, size=(10, 40))
    out = tmp_path / "many.png"
    plot_mcmc_traces(chain, log_prob, ['lambda_F'], max_walkers=5,
                     out_file=str(out))
    assert out.stat().st_size > 0


# ----------------------------------------------------------------------------
# Legacy text results
# ----------------------------------------------------------------------------

def test_legacy_text_directory_is_still_readable(tmp_path):
    """Old mcmc_output/ directories must keep loading, walker count inferred."""
    from card import load_legacy_text_results

    n_walkers, n_steps, ndim = 8, 10, 2
    samples = np.arange(n_walkers * n_steps * ndim, dtype=float).reshape(-1, ndim)
    np.savetxt(tmp_path / "samples.txt", samples)
    np.savetxt(tmp_path / "log_probs.txt", np.zeros(n_walkers * n_steps))
    (tmp_path / "param_names.txt").write_text("lambda_F\nk_F\n")

    results = load_legacy_text_results(str(tmp_path))
    assert results['param_names'] == ['lambda_F', 'k_F']
    assert results['chain'].shape == (n_steps, n_walkers, ndim)


# ----------------------------------------------------------------------------
# Embedding in a GUI
# ----------------------------------------------------------------------------

def test_return_figure_hands_back_an_open_figure():
    """Streamlit's st.pyplot, a Qt canvas and a notebook all want the Figure
    object.  A library that closes it first is awkward to embed."""
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    fig = plot_lambda_history(GeneralModel.flood_only(lambda_F=1e5, k_F=1e-2),
                              n_points=30, out_file=None, return_figure=True)
    assert isinstance(fig, Figure)
    assert plt.fignum_exists(fig.number), "the figure was closed"
    plt.close(fig)


@pytest.mark.parametrize("plot", ["age", "lambda", "sweep"])
def test_every_age_curve_figure_can_be_returned(plot, tmp_path):
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    call = {
        "age": lambda: plot_age_comparison(n_points=20, out_file=None,
                                           return_figure=True),
        "lambda": lambda: plot_lambda_history(
            GeneralModelParams.defaults(), n_points=20, out_file=None,
            return_figure=True),
        "sweep": lambda: plot_general_model_parameter_sweep(
            vary_params={'lambda_F': [1e5]}, n_points=20, out_file=None,
            return_figure=True),
    }[plot]
    fig = call()
    assert isinstance(fig, Figure)
    plt.close(fig)


def test_chain_figures_can_be_returned(fake_chain):
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    chain, log_prob, names = fake_chain
    corner = plot_mcmc_corner(chain.reshape(-1, 2), names, out_file=None,
                              return_figure=True)
    traces = plot_mcmc_traces(chain, log_prob, names, out_file=None,
                              return_figure=True)
    assert isinstance(corner, Figure) and isinstance(traces, Figure)
    plt.close(corner)
    plt.close(traces)


def test_the_default_is_still_a_path(tmp_path):
    """Opt-in only: existing callers, the examples and the paper must be
    unaffected, and must not leak open figures."""
    import matplotlib.pyplot as plt

    before = len(plt.get_fignums())
    out = tmp_path / "unchanged.png"
    assert plot_lambda_history(GeneralModelParams.defaults(), n_points=20,
                               out_file=str(out)) == str(out)
    assert len(plt.get_fignums()) == before
