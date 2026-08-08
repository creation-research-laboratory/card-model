"""
The Python side of the worker boundary.

Deliberately thin.  Everything of substance lives in `card`, which is already
tested; this file only converts plain dicts into package calls and back, so
there is no second implementation of anything to keep in sync.

Kept as a real .py file rather than a string inside the worker so it is
lintable, diffable, and importable from pytest.
"""

import json
import time

from card.calibrate import solve_flood_only
from card.chronology import Chronology


def calibrate(spec_json: str) -> str:
    """
    Solve the flood-only model for one preset or one custom input set.

    Args:
        spec_json: JSON object with `chronology` (a Chronology dict),
            `flood_secular_age`, and `second_secular_age`.

    Returns:
        JSON object with the solved parameters, the residuals, and the wall
        time the solve itself took.
    """
    spec = json.loads(spec_json)
    chronology = Chronology.from_dict(spec["chronology"])

    started = time.perf_counter()
    result = solve_flood_only(
        flood_age=chronology.flood_start_age,
        flood_secular_age=float(spec["flood_secular_age"]),
        second_age=chronology.ice_age_end_age,
        second_secular_age=float(spec["second_secular_age"]),
        chronology=chronology,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    return json.dumps({
        "lambda_F": result.lambda_F,
        "k_F": result.k_F,
        "residuals": list(result.residuals),
        "max_abs_residual": result.max_abs_residual,
        "flood_date": result.flood_date,
        "solve_ms": elapsed_ms,
    })


def series(spec_json: str) -> str:
    """
    Sample the calibrated model, the way a chart or a CSV export would.

    Exists in the spike only to check that a realistic workload — hundreds of
    `forward_age` evaluations, not one — is still fast enough to sit behind a
    dragged slider.
    """
    spec = json.loads(spec_json)
    chronology = Chronology.from_dict(spec["chronology"])
    n = int(spec.get("n", 400))

    result = solve_flood_only(
        flood_age=chronology.flood_start_age,
        flood_secular_age=float(spec["flood_secular_age"]),
        second_age=chronology.ice_age_end_age,
        second_secular_age=float(spec["second_secular_age"]),
        chronology=chronology,
    )
    model = result.model
    present = chronology.present_date

    started = time.perf_counter()
    # Log-spaced in true age: the structure is all in the recent end, and a
    # linear grid spends every point on the flat tail.
    lo, hi = 1.0, present
    step = (hi / lo) ** (1.0 / (n - 1))
    rows = []
    age = lo
    for _ in range(n):
        rows.append((age, model.forward_age(age, present)))
        age *= step
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    return json.dumps({
        "n": len(rows),
        "first": rows[0],
        "last": rows[-1],
        "series_ms": elapsed_ms,
    })


def environment() -> str:
    """Report what the interpreter actually loaded — the payload claim, checked."""
    import sys

    return json.dumps({
        "python": sys.version.split()[0],
        "card_version": __import__("card").__version__,
        "numpy_loaded": "numpy" in sys.modules,
        "scipy_loaded": "scipy" in sys.modules,
    })
