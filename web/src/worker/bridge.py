"""
The Python side of the worker boundary.

Deliberately thin: dicts in, dicts out. Everything of substance lives in
`card`, which is already tested, so there is no second implementation of the
model to keep in sync — that is the entire reason for running the real package
in the browser instead of porting it.

Kept as a real .py file rather than a string inside the worker so it is
lintable, diffable, and importable from pytest.

Naming follows the package's rule: `_age` is an AGE (years before present),
`_date` is a DATE (years after Day 1 of Creation).
"""

from __future__ import annotations

import json
import warnings
from typing import Any, Dict, List

from card.calibrate import solve_flood_only
from card.chronology import Chronology
from card.models import GeneralModel, GeneralModelParams
from card.parameters import (
    parameter_specs,
    split_fixed_and_free,
    to_json_schema,
)

__all__ = ["calibrate", "series", "lambda_history", "geologic_column",
           "forward_age", "inverse_age", "schema", "environment"]


#: Relative offset used to place a sample just past a discontinuity.  Large
#: enough to survive being rounded to 9 significant figures for the file, small
#: enough to be invisible on a chart spanning thousands of years (~0.0002 yr at
#: the Flood).
_STEP_EPSILON = 1e-7


def _just_after(date: float) -> float:
    """The smallest DATE past `date` that still round-trips through the file."""
    return date * (1.0 + _STEP_EPSILON) if date > 0.0 else _STEP_EPSILON


def _flood_end(model: GeneralModel, chronology: Chronology,
               secular: float, present: float) -> Dict[str, Any]:
    """Where a Flood-boundary model lands on the calibrated curve."""
    if secular > model.max_secular_age(present):
        return {"secularAge": secular, "inRange": False}
    true_age = model.inverse_age(secular, present)
    after = chronology.flood_start_age - true_age
    return {"secularAge": secular, "inRange": True, "trueAge": true_age,
            "yearsAfterFlood": after, "floodDays": after * 365.25}


def _chronology(spec: Dict[str, Any]) -> Chronology:
    return Chronology(
        age_of_earth=float(spec["ageOfEarth"]),
        flood_start_date=float(spec["floodStartDate"]),
        flood_end_date=float(spec["floodEndDate"]),
        ice_age_end_date=float(spec["iceAgeEndDate"]),
    )


def _ok(payload: Dict[str, Any], captured: List[warnings.WarningMessage]) -> str:
    """
    Wrap a successful result, carrying any warnings through to the UI.

    `GeneralModelParams` warns rather than raises for two conditions — a Flood
    longer than 2 years, and a non-unit lambda_bg. Those are exactly the things
    a user fiddling with sliders should see, and dropping them on the floor
    would make the browser quieter than the CLI about the same input.
    """
    payload["warnings"] = [str(w.message) for w in captured]
    return json.dumps(payload)


def _error(exc: Exception) -> str:
    """
    Surface the package's own prose.

    `card` raises ValueError with messages written for a human — they explain
    the DATE/AGE distinction, why a rate below 1 is meaningless, and so on.
    Re-wording them here would be strictly worse.
    """
    return json.dumps({
        "error": {"type": type(exc).__name__, "message": str(exc)},
    })


def calibrate(request_json: str) -> str:
    """Solve the flood-only model against the two matched date pairs."""
    try:
        request = json.loads(request_json)
        chronology = _chronology(request["chronology"])
        overrides = request.get("overrides") or {}

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            # Both matched pairs are the ends of the Flood: it begins at the
            # pre-Flood/Flood boundary and ends at the selected
            # Flood/post-Flood one.
            # Two matched pairs: the Precambrian-Cambrian boundary at the
            # Flood's beginning, and the conventional Ice Age endpoint at the
            # chronology's Ice Age date.  The Flood-end model (K/Pg or N/Q)
            # does not enter here -- it is read off the result.
            flood_age = chronology.flood_start_age
            second_age = chronology.ice_age_end_age
            result = solve_flood_only(
                flood_age=flood_age,
                flood_secular_age=float(request["floodStartSecularAge"]),
                second_age=second_age,
                second_secular_age=float(request["iceAgeSecularAge"]),
                chronology=chronology,
                k_F_bracket=(1e-9, 100.0),
            )
            params = result.model.params

            # Overrides apply on top of the solve. The Creation-week parameters
            # do not enter either constraint (both constraint ages map to
            # formation DATEs at or after t_F), so overriding them cannot
            # invalidate the residuals reported below — which is what makes the
            # general mode a data change rather than a new solver.
            if overrides:
                merged = params.to_dict()
                merged.update({k: float(v) for k, v in overrides.items()})
                params = GeneralModelParams.from_dict(merged)

            model = GeneralModel(params)
            present = chronology.present_date

            return _ok({
                "params": params.to_dict(),
                "residuals": list(result.residuals),
                "maxAbsResidual": result.max_abs_residual,
                "maxSecularAge": model.max_secular_age(present),
                "floodDate": result.flood_date,
                "floodStartAge": chronology.flood_start_age,
                "iceAgeEndAge": chronology.ice_age_end_age,
                # An output: where the selected Flood-end model lands on this
                # calibrated curve.
                "floodEnd": _flood_end(model, chronology,
                                       float(request["floodEndSecularAge"]),
                                       present),
            }, caught)
    except Exception as exc:  # noqa: BLE001 — the boundary reports, never crashes
        return _error(exc)


def series(request_json: str) -> str:
    """
    Sample the calibrated curve on a log-spaced grid.

    Breakpoints and constraint ages are unioned in for the same reason the
    generator does it: without them the Flood discontinuity draws as a diagonal
    and the calibration anchors are interpolated rather than exact.
    """
    try:
        request = json.loads(request_json)
        chronology = _chronology(request["chronology"])
        params = GeneralModelParams.from_dict(request["params"])
        model = GeneralModel(params)
        present = chronology.present_date
        n = max(2, int(request.get("points", 400)))

        lo, hi = 1.0, present
        ratio = (hi / lo) ** (1.0 / (n - 1))
        grid = {lo * ratio ** i for i in range(n)}
        grid.update({0.0, present})
        for date in model.breakpoints():
            age = chronology.date_to_age(date)
            if 0.0 < age < present:
                grid.add(age)
                grid.add(age * (1.0 - 1e-12))
        for age in request.get("anchors", []):
            if 0.0 <= float(age) <= present:
                grid.add(float(age))

        ordered = sorted(grid)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            secular = [model.forward_age(age, present) for age in ordered]
            return _ok({"trueAge": ordered, "secularAge": secular}, caught)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def lambda_history(request_json: str) -> str:
    """
    Sample lambda(t) against DATE — the decay-rate history.

    Mirrors `card.plotting.plot_lambda_history`: linear in DATE from 0 to the
    present, log in lambda.  This is the one curve whose x axis is a DATE
    (years after Day 1 of Creation) rather than an AGE, and a UI must say so.

    Unlike the age curve, this one is genuinely discontinuous: `forward_age` is
    the integral of a bounded rate and so is continuous, but lambda itself
    steps at t_c, t_F and t_F2.  Each breakpoint therefore needs *two* samples —
    one at the breakpoint and one just after it — or a chart draws the Flood as
    a diagonal ramp instead of a jump.  `lambda_func` uses `<=`, so the value
    at a breakpoint belongs to the earlier region and the partner sample has to
    be on the later side.
    """
    try:
        request = json.loads(request_json)
        chronology = _chronology(request["chronology"])
        params = GeneralModelParams.from_dict(request["params"])
        model = GeneralModel(params)
        present = chronology.present_date
        n = max(2, int(request.get("points", 400)))

        step = present / (n - 1)
        grid = {i * step for i in range(n)}
        grid.update({0.0, present})
        for date in model.breakpoints():
            if 0.0 <= date <= present:
                grid.add(date)
                after = _just_after(date)
                if after <= present:
                    grid.add(after)
                # A linear grid cannot resolve the relaxation: k_F reaches
                # ~2/yr here, so lambda is back at background within about five
                # years while a 400-point grid over six millennia samples every
                # fifteen.  Log-spaced points from the breakpoint capture the
                # shape for any decay constant.
                span = present - date
                if span > 0:
                    lo = max(1e-4, span * 1e-9)
                    steps = 120
                    ratio = (span / lo) ** (1.0 / (steps - 1))
                    grid.update(date + lo * ratio ** i for i in range(steps))

        ordered = sorted(grid)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            rates = [model.lambda_func(t) for t in ordered]
            return _ok({
                "date": ordered,
                "lambda": rates,
                # Handed over so a chart can mark the Flood without
                # re-deriving it from the parameters.
                "floodStartDate": params.t_F,
                "floodEndDate": params.t_F2,
                "presentDate": present,
            }, caught)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def geologic_column(request_json: str) -> str:
    """
    Each chronostratigraphic unit's secular span, as a young-earth duration.

    The unit catalogue is passed in rather than read from a file: the browser
    already has it, and `card` has no business knowing about the ICS chart.

    Durations are *differences* of inverse ages, and the older units differ
    only in the fourth or fifth significant figure — which is why the
    precomputed layer cannot approximate this view and ships exact numbers
    instead.  The same reasoning is why this returns durations rather than
    endpoints for the caller to subtract.
    """
    try:
        request = json.loads(request_json)
        chronology = _chronology(request["chronology"])
        model = GeneralModel(GeneralModelParams.from_dict(request["params"]))
        present = chronology.present_date
        max_secular = model.max_secular_age(present)

        rows: List[Dict[str, Any]] = []
        younger_secular = 0.0
        younger_true = 0.0
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for unit in request["units"]:
                base_secular = float(unit["baseSecularAge"])
                row: Dict[str, Any] = {
                    "name": unit["name"],
                    "rank": unit.get("rank", "period"),
                    "baseSecularAge": base_secular,
                    "topSecularAge": younger_secular,
                }
                if base_secular <= max_secular:
                    base_true = model.inverse_age(base_secular, present)
                    duration = base_true - younger_true
                    row.update({
                        "inRange": True,
                        "baseTrueAge": base_true,
                        "topTrueAge": younger_true,
                        "durationTrue": duration,
                        "acceleration": ((base_secular - younger_secular) / duration
                                         if duration > 0 else None),
                    })
                    younger_true = base_true
                else:
                    row["inRange"] = False
                younger_secular = base_secular
                rows.append(row)
            return _ok({"units": rows, "maxSecularAge": max_secular}, caught)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def forward_age(request_json: str) -> str:
    """Apparent secular age for a true age."""
    try:
        request = json.loads(request_json)
        chronology = _chronology(request["chronology"])
        model = GeneralModel(GeneralModelParams.from_dict(request["params"]))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = model.forward_age(float(request["trueAge"]),
                                      chronology.present_date)
            return _ok({"value": value}, caught)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def inverse_age(request_json: str) -> str:
    """True age that would appear as the given secular age."""
    try:
        request = json.loads(request_json)
        chronology = _chronology(request["chronology"])
        model = GeneralModel(GeneralModelParams.from_dict(request["params"]))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = model.inverse_age(float(request["secularAge"]),
                                      chronology.present_date)
            return _ok({"value": value}, caught)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def schema(request_json: str) -> str:
    """
    Parameter metadata for the input form, straight from the package.

    This is the payoff for running real `card` in the browser: add a parameter
    to `GeneralModelParams` and a control appears with no frontend change,
    because the bounds, units, log-scale flags and tooltips all come from the
    `ParamSpec` declared on the dataclass field. Date bounds follow the loaded
    chronology rather than the one frozen in at import time.
    """
    try:
        request = json.loads(request_json)
        chronology = _chronology(request["chronology"])
        fixed = request.get("fixed") or {}

        # Resolve chronology *names* the way run configs do, so a mode can say
        # `t_F: flood_start_date` and stay correct across chronologies.
        resolved: Dict[str, float] = {}
        for name, value in fixed.items():
            if isinstance(value, str):
                resolved[name] = float(getattr(chronology, value))
            else:
                resolved[name] = float(value)

        free, pinned = split_fixed_and_free(GeneralModelParams, resolved)
        specs = parameter_specs(GeneralModelParams)

        return json.dumps({
            "schema": to_json_schema(GeneralModelParams, chronology=chronology),
            "free": list(free),
            "fixed": {name: resolved[name] for name in pinned},
            # `is_fittable` is false when minimum == maximum (lambda_bg), so a
            # UI skips it structurally rather than by a hardcoded exclusion.
            "fittable": [n for n, s in specs.items() if s.is_fittable],
            "warnings": [],
        })
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


def environment() -> str:
    """Report what the interpreter loaded — the stdlib-only claim, checked."""
    import sys

    import card

    return json.dumps({
        "python": sys.version.split()[0],
        "cardVersion": card.__version__,
        "numpyLoaded": "numpy" in sys.modules,
        "scipyLoaded": "scipy" in sys.modules,
        "warnings": [],
    })
