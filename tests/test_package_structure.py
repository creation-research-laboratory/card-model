"""
Tests for package structure: lazy imports, the deprecation shim, and the
extension path for new models.

The lazy-import tests run in a subprocess because they assert on the contents
of `sys.modules` immediately after `import card`, which cannot be observed
once the test session has already imported everything.
"""

import subprocess
import sys
import textwrap
import warnings

import numpy as np
import pytest

from card import DecayModel, GeneralModel, GeneralModelParams


def run_snippet(source: str) -> str:
    """Execute source in a clean interpreter and return its stdout."""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


# ----------------------------------------------------------------------------
# Lazy imports
# ----------------------------------------------------------------------------

def test_importing_card_pulls_in_nothing_heavy():
    """`import card` must not drag in plotting or MCMC dependencies — that is
    the whole point of the lazy __getattr__, and what lets a browser or
    headless build use the models without them installed."""
    loaded = run_snippet("""
        import sys
        import card
        heavy = [name for name in
                 ('numpy', 'scipy', 'matplotlib', 'emcee', 'corner',
                  'card.models', 'card.plotting', 'card.card_mcmc')
                 if name in sys.modules]
        print(','.join(heavy))
    """)
    assert loaded == ""


def test_model_access_loads_only_the_numerical_core():
    """Touching a model brings in numpy/scipy but still not matplotlib."""
    loaded = run_snippet("""
        import sys
        import card
        card.GeneralModel
        print('numpy' in sys.modules,
              'matplotlib' in sys.modules,
              'emcee' in sys.modules)
    """)
    assert loaded == "True False False"


def test_fitter_access_does_not_load_emcee_or_h5py():
    """The fitter's heavy dependencies are imported inside the methods that
    need them, so holding a reference to MCMCFitter costs nothing."""
    loaded = run_snippet("""
        import sys
        import card
        card.MCMCFitter
        print('emcee' in sys.modules, 'h5py' in sys.modules)
    """)
    assert loaded == "False False"


def test_calibration_does_not_need_a_plotting_stack():
    loaded = run_snippet("""
        import sys
        import card
        card.solve_flood_only
        print('matplotlib' in sys.modules, 'emcee' in sys.modules)
    """)
    assert loaded == "False False"


def test_plotting_access_loads_matplotlib_on_demand():
    loaded = run_snippet("""
        import sys
        import card
        assert 'matplotlib' not in sys.modules
        card.plot_age_comparison
        print('matplotlib' in sys.modules)
    """)
    assert loaded == "True"


def test_from_import_works_like_an_eager_import():
    out = run_snippet("""
        from card import GeneralModel, FLOOD_AGE
        print(GeneralModel.__name__, FLOOD_AGE)
    """)
    assert out == "GeneralModel 4400.0"


def test_repeated_access_is_cached():
    """The first lookup caches into module globals, so the second is a plain
    attribute read rather than another import."""
    out = run_snippet("""
        import card
        first = card.GeneralModel
        assert 'GeneralModel' in vars(card)
        print(first is card.GeneralModel)
    """)
    assert out == "True"


def test_loading_a_run_config_stays_light():
    """`card.config` is stdlib plus chronology, so a GUI or a web service can
    parse and validate a run config without the numerical stack installed."""
    loaded = run_snippet("""
        import sys
        from card.config import RunConfig
        RunConfig.from_dict({'constraints': [
            {'young_age': 'flood_start_age', 'secular_age': 5.4e8,
             'uncertainty': 1e7}]})
        heavy = [name for name in ('numpy', 'scipy', 'matplotlib', 'emcee',
                                   'h5py', 'card.models')
                 if name in sys.modules]
        print(','.join(heavy))
    """)
    assert loaded == ""


def test_cli_help_does_not_import_the_numerical_stack():
    """`card --help` and `card schema` must not pay for emcee or matplotlib;
    each command imports what it needs inside itself."""
    loaded = run_snippet("""
        import sys
        from card.cli import main
        try:
            main(['--help'])
        except SystemExit:
            pass
        heavy = [name for name in ('matplotlib', 'emcee', 'corner', 'h5py')
                 if name in sys.modules]
        # Tagged, because argparse has already printed the help text above.
        print('HEAVY:' + ','.join(heavy))
    """)
    assert loaded.splitlines()[-1] == "HEAVY:"


def test_unknown_attribute_raises_attribute_error():
    import card

    with pytest.raises(AttributeError, match="has no attribute 'NoSuchName'"):
        card.NoSuchName


def test_dir_lists_the_public_api():
    import card

    names = dir(card)
    for expected in ("GeneralModel", "Chronology", "MCMCFitter", "ParamSpec",
                     "solve_flood_only", "plot_age_comparison",
                     "AGE_OF_EARTH", "__version__"):
        assert expected in names


def test_deprecated_names_are_not_in_the_public_api():
    """CARDMCMC still resolves via the shim, but is no longer advertised."""
    import card

    assert "CARDMCMC" not in card.__all__


def test_all_names_actually_resolve():
    """Every name advertised in __all__ must be importable — a typo in the
    lazy-export table would otherwise only surface at a user's call site."""
    import card

    for name in card.__all__:
        assert getattr(card, name) is not None


# ----------------------------------------------------------------------------
# Deprecation shim
# ----------------------------------------------------------------------------

def test_decay_solver_import_warns():
    out = run_snippet("""
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            import card.decay_solver  # noqa: F401
        print(any(issubclass(w.category, DeprecationWarning) for w in caught))
    """)
    assert out == "True"


def test_decay_solver_reexports_the_same_objects():
    import card

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import card.decay_solver as shim

    assert shim.GeneralModel is card.GeneralModel
    assert shim.GeneralModelParams is card.GeneralModelParams
    assert shim.ConstantDecayModel is card.ConstantDecayModel
    assert shim.AGE_OF_EARTH == card.AGE_OF_EARTH
    assert shim.plot_age_comparison is card.plot_age_comparison


# ----------------------------------------------------------------------------
# Extension path: a new model should only need lambda_func
# ----------------------------------------------------------------------------

class LinearRampModel(DecayModel):
    """A continuous toy model: lambda rises linearly with time."""

    def lambda_func(self, t):
        return 1.0 + t / 1000.0


class TwoStepModel(DecayModel):
    """A discontinuous toy model, to exercise the breakpoint machinery."""

    def __init__(self, step_date, high):
        self.step_date = step_date
        self.high = high

    def lambda_func(self, t):
        return self.high if t <= self.step_date else 1.0

    def breakpoints(self):
        return (self.step_date,)


def test_new_model_only_needs_lambda_func():
    """Everything else — integral, forward, inverse, domain checks — comes
    from the base class."""
    model = LinearRampModel()
    present = 6056.0

    for true_age in (0.0, 100.0, 3000.0, present):
        t_f = present - true_age
        exact = (present - t_f) + (present ** 2 - t_f ** 2) / 2000.0
        assert model.forward_age(true_age) == pytest.approx(exact, rel=1e-9)

    secular = model.forward_age(2000.0)
    assert model.inverse_age(secular) == pytest.approx(2000.0, rel=1e-9)


def test_base_class_enforces_the_same_error_contract():
    model = LinearRampModel()
    with pytest.raises(ValueError, match="must be >= 0"):
        model.forward_age(-1.0)
    with pytest.raises(ValueError, match="exceeds present_time"):
        model.forward_age(1e9)
    with pytest.raises(ValueError, match="exceeds the maximum"):
        model.inverse_age(1e12)


def test_breakpoints_are_used_by_the_fallback_quadrature():
    """Integrating across a discontinuity without breakpoints is exactly the
    bug that motivated the closed-form GeneralModel; the base class must not
    reintroduce it for models that declare where they jump."""
    step, high = 1656.0, 1e5
    model = TwoStepModel(step_date=step, high=high)
    present = 6056.0

    # Rock formed on Day 1: high rate up to the step, background after.
    exact = high * step + (present - step)
    assert model.forward_age(present, present) == pytest.approx(exact, rel=1e-8)


def test_abstract_model_cannot_be_instantiated():
    with pytest.raises(TypeError):
        DecayModel()


def test_general_model_declares_its_discontinuities():
    params = GeneralModelParams(lambda_c=1e3, lambda_F=1e5, lambda_bg=1.0,
                                k_c=1e-1, k_F=8.04e-3,
                                t_c=1, t_F=1656, t_F2=1657)
    assert GeneralModel(params).breakpoints() == (1, 1656, 1657)


def test_general_model_requires_validated_params():
    """Passing a bare dict would bypass __post_init__ validation entirely."""
    with pytest.raises(ValueError, match="requires a GeneralModelParams"):
        GeneralModel({"lambda_c": 1.0})
