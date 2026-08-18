"""
Calibrated time series, and the CSV a reader can take away.

One function behind both the ``card series`` subcommand and the browser's
download button, so a file fetched from the web app and one produced by a
local CLI run are byte-for-byte identical.  That is a testable claim rather
than an aspiration -- `tests/test_series.py` pins it -- and it is the reason
the formatting decisions below are as fussy as they are.

**Stdlib only**, like `models.py` and `calibrate.py`.  This runs inside
Pyodide, where numpy and scipy would cost 16 MB against a 5.8 MB runtime.

Two things make the output reproducible:

* Numbers are written with `repr`, which since Python 3.1 is the *shortest*
  string that round-trips to the same float.  Rounding to a fixed number of
  decimals would silently discard precision the model has, and ``%.17g`` would
  add digits that are noise.
* The generation timestamp is an argument, not a call to `now()`.  It is the
  only value in the file that cannot be derived from the model, so it is the
  only one a caller has to supply to get a deterministic result.

The provenance header is not decoration.  With free parameters, most downloads
will describe a model that exists nowhere else, and a CSV that leaves the page
without its chronology and parameters is an unreproducible number.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence, Tuple

from .chronology import Chronology
from .models import GeneralModel

__all__ = [
    "SeriesConstraint",
    "COLUMNS",
    "sample_ages",
    "series_rows",
    "to_csv",
]

#: Column order.  The ``_ybp``/``_yac`` suffixes carry the convention, so a
#: DATE cannot be mistaken for an AGE once the file has left the app.
COLUMNS: Tuple[str, ...] = (
    "true_age_ybp",
    "formation_date_yac",
    "secular_age_yr",
    "lambda_at_formation",
    "acceleration_ratio",
)


@dataclass(frozen=True)
class SeriesConstraint:
    """
    One matched date pair, as the header reports it.

    Deliberately not `config.Constraint`: this module is imported by the
    browser bridge, which builds its constraints from a JSON request and has
    no run config at all.
    """

    label: str
    true_age: float
    secular_age: float
    residual: float


def sample_ages(
    model: GeneralModel,
    chronology: Chronology,
    points: int = 400,
    anchors: Iterable[float] = (),
) -> List[float]:
    """
    Log-spaced true ages to evaluate the model at.

    Log-spaced because the structure is all at the recent end: a linear grid
    over six thousand years spends almost every point on the flat tail and
    none inside the Flood year, where lambda falls by four orders of
    magnitude.

    Two unions on top of it.  The model's breakpoints, plus a sample a hair
    inside each, so the discontinuity at ``t_F`` renders as a step rather than
    a diagonal joining the two sides.  And the caller's anchors -- the
    constraint ages -- so the calibration's own targets are exact rows instead
    of interpolated ones.

    Args:
        model: A calibrated model.
        chronology: Supplies ``present_date`` and the DATE/AGE conversion.
        points: Size of the log-spaced grid before the unions; the result is
            a little larger.
        anchors: True ages (YBP) that must appear exactly.

    Returns:
        Ascending true ages, from 0 to ``present_date``.
    """
    present = chronology.present_date
    n = max(2, int(points))

    lo, hi = 1.0, present
    ratio = (hi / lo) ** (1.0 / (n - 1))
    # Clamped, because `lo * ratio ** (n - 1)` is only *approximately* `hi`:
    # at 200 points it lands 9e-11 above `present_date`, and `forward_age`
    # rejects a true age past the present as a formation before Day 1. The
    # default of 400 happens to round the other way, which is why the charts
    # never hit this.
    grid = {a for a in (lo * ratio ** i for i in range(n)) if a < present}
    grid.update({0.0, present})

    for date in model.breakpoints():
        age = chronology.date_to_age(date)
        if 0.0 < age < present:
            grid.add(age)
            # A hair *younger*, which is the far side of the jump: age falls as
            # DATE rises, so this lands just inside the phase the breakpoint
            # opens.
            grid.add(age * (1.0 - 1e-12))

    for age in anchors:
        age = float(age)
        if 0.0 <= age <= present:
            grid.add(age)

    return sorted(grid)


def series_rows(
    model: GeneralModel,
    chronology: Chronology,
    ages: Sequence[float],
) -> List[Tuple[float, float, float, float, Optional[float]]]:
    """
    Evaluate the model at each age, in `COLUMNS` order.

    ``acceleration_ratio`` is the *cumulative* one -- secular years of
    apparent age per true year elapsed since formation -- which is what a
    reader comparing a rock's published age to its young-earth age wants. It
    is not ``lambda_at_formation``, which is the instantaneous rate at the
    moment of formation; the two differ by everything that happened since.
    Undefined at the present, where both ages are zero, and reported as blank
    rather than as a made-up limit.
    """
    present = chronology.present_date
    rows = []
    for age in ages:
        date = chronology.age_to_date(age)
        secular = model.forward_age(age, present)
        lam = model.lambda_func(date)
        ratio = secular / age if age > 0 else None
        rows.append((age, date, secular, lam, ratio))
    return rows


def _num(value: Optional[float]) -> str:
    """Shortest round-tripping form, or empty for an undefined cell."""
    return "" if value is None else repr(float(value))


def to_csv(
    model: GeneralModel,
    chronology: Chronology,
    *,
    points: int = 400,
    constraints: Sequence[SeriesConstraint] = (),
    description: str = "custom parameters",
    generated: Optional[datetime] = None,
    version: Optional[str] = None,
) -> str:
    """
    The whole file: provenance header, column names, rows.

    Args:
        model: A calibrated model.
        chronology: The chronology it was calibrated against.
        points: Grid size before the breakpoint and anchor unions.
        constraints: Reported in the header, and their ages become exact rows.
        description: What produced this -- a preset's name, or the default
            saying the parameters came from somewhere else.
        generated: Timestamp for the header.  Defaults to now, in UTC; pass it
            explicitly for a deterministic file.
        version: Package version for the header.  Defaults to the installed
            one.

    Returns:
        CSV text with ``\\n`` line endings and a trailing newline.

    Note:
        ``#`` comment lines are read as comments by pandas (``comment='#'``)
        and R (``comment.char='#'``), but **not** by Excel, which shows them
        as rows.
    """
    if version is None:
        from . import __version__ as version
    stamp = (generated or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")

    params = model.params
    lines = [
        "# CARD calibrated time series",
        f"# generated: {stamp}   card {version}",
        f"# source: {description}",
        "# chronology: "
        f"age_of_earth={_num(chronology.age_of_earth)} "
        f"flood_start_date={_num(chronology.flood_start_date)} "
        f"flood_end_date={_num(chronology.flood_end_date)} "
        f"ice_age_end_date={_num(chronology.ice_age_end_date)}",
        "# parameters: "
        f"lambda_c={_num(params.lambda_c)} k_c={_num(params.k_c)} "
        f"t_c={_num(params.t_c)} "
        f"lambda_F={_num(params.lambda_F)} k_F={_num(params.k_F)} "
        f"t_F={_num(params.t_F)} t_F2={_num(params.t_F2)} "
        f"k_PF={_num(params.k_PF)} lambda_bg={_num(params.lambda_bg)}",
        # Pinned by continuity at t_F2 rather than free, so it is reported
        # separately -- feeding it back in as a parameter would not round-trip.
        f"# lambda_F2: {_num(params.lambda_F2)} "
        "(pinned by continuity at t_F2, not an independent parameter)",
    ]
    for c in constraints:
        lines.append(
            f"# constraint: {c.label}: {_num(c.true_age)} YBP -> "
            f"{_num(c.secular_age)} yr apparent (relative residual "
            f"{c.residual:+.1e})"
        )

    lines.append(",".join(COLUMNS))

    ages = sample_ages(model, chronology, points,
                       anchors=[c.true_age for c in constraints])
    for row in series_rows(model, chronology, ages):
        lines.append(",".join(_num(v) for v in row))

    return "\n".join(lines) + "\n"
