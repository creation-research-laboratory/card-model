"""
The downloadable time series.

Two properties carry most of the weight.  The calibration's own anchors have
to be *exact rows* rather than interpolated neighbours, because a reader
checking the file against a published boundary age will look them up first.
And the file has to be reproducible: the same model and the same timestamp
must give the same bytes, or the claim that a browser download equals a CLI
run is untestable.
"""

import csv
import io
import math
from datetime import datetime, timezone

import pytest

from card.calibrate import solve_flood_rate
from card.chronology import DEFAULT_CHRONOLOGY, Chronology
from card.series import (
    COLUMNS, SeriesConstraint, sample_ages, series_rows, to_csv,
)

STAMP = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def solved():
    """The shipped three-pair calibration, and the constraints it honoured."""
    chronology = DEFAULT_CHRONOLOGY
    result = solve_flood_rate(
        pre_flood_secular_age=541e6,
        post_flood_secular_age=66e6,
        ice_age_secular_age=12000.0,
        chronology=chronology,
    )
    constraints = [
        SeriesConstraint("Flood begins", chronology.flood_start_age,
                         541e6, result.residuals[0]),
        SeriesConstraint("Flood ends", chronology.flood_end_age,
                         66e6, result.residuals[1]),
        SeriesConstraint("Ice Age ends", chronology.ice_age_end_age,
                         12000.0, result.residuals[2]),
    ]
    return result.model, chronology, constraints


def parse(text):
    """Header comment lines, and the data as dicts."""
    header = [ln for ln in text.splitlines() if ln.startswith("#")]
    body = "\n".join(ln for ln in text.splitlines() if not ln.startswith("#"))
    return header, list(csv.DictReader(io.StringIO(body)))


# ------------------------------------------------------------------ anchors
class TestAnchors:
    def test_every_constraint_is_an_exact_row(self, solved):
        model, chronology, constraints = solved
        _, rows = parse(to_csv(model, chronology, points=200,
                               constraints=constraints, generated=STAMP))
        ages = [float(r["true_age_ybp"]) for r in rows]
        for c in constraints:
            assert c.true_age in ages, f"{c.label} is not a row"

    def test_the_anchor_row_reproduces_the_target(self, solved):
        # The point of the exercise: a reader looking up 4400 YBP must find
        # 541 Myr, not an interpolation between neighbouring grid points.
        model, chronology, constraints = solved
        _, rows = parse(to_csv(model, chronology, points=200,
                               constraints=constraints, generated=STAMP))
        by_age = {float(r["true_age_ybp"]): r for r in rows}
        for c in constraints:
            got = float(by_age[c.true_age]["secular_age_yr"])
            assert abs(got / c.secular_age - 1) < 1e-9, c.label

    def test_a_coarse_grid_still_lands_the_anchors(self, solved):
        # They are unioned in, not hoped for, so grid size cannot lose them.
        model, chronology, constraints = solved
        _, rows = parse(to_csv(model, chronology, points=8,
                               constraints=constraints, generated=STAMP))
        ages = [float(r["true_age_ybp"]) for r in rows]
        for c in constraints:
            assert c.true_age in ages


# --------------------------------------------------------------------- grid
class TestGrid:
    def test_ascending_and_bounded(self, solved):
        model, chronology, _ = solved
        ages = sample_ages(model, chronology, 100)
        assert ages == sorted(ages)
        assert len(set(ages)) == len(ages)
        assert ages[0] == 0.0
        assert ages[-1] == chronology.present_date

    def test_straddles_every_breakpoint(self, solved):
        # Without a sample either side, the jump at t_F draws as a diagonal
        # joining the pre-Flood and in-Flood values.
        model, chronology, _ = solved
        ages = sample_ages(model, chronology, 100)
        for date in model.breakpoints():
            age = chronology.date_to_age(date)
            if not 0.0 < age < chronology.present_date:
                continue
            assert any(a < age for a in ages)
            assert any(a > age for a in ages)
            assert age in ages

    def test_log_spaced_not_linear(self, solved):
        # A linear grid over six thousand years puts no point inside the Flood
        # year, where lambda falls by four orders of magnitude.
        model, chronology, _ = solved
        ages = sample_ages(model, chronology, 400)
        recent = [a for a in ages if 0 < a <= 10]
        assert len(recent) > 20, "a linear grid would have ~1 point below 10 yr"


# ------------------------------------------------------------------- values
class TestValues:
    def test_columns_are_the_declared_ones(self, solved):
        model, chronology, _ = solved
        _, rows = parse(to_csv(model, chronology, points=20, generated=STAMP))
        assert tuple(rows[0].keys()) == COLUMNS

    def test_date_and_age_are_complements(self, solved):
        # The convention the suffixes advertise: a DATE and its AGE sum to the
        # age of the Earth. Conflating them is a documented past bug.
        model, chronology, _ = solved
        _, rows = parse(to_csv(model, chronology, points=50, generated=STAMP))
        for r in rows:
            total = float(r["true_age_ybp"]) + float(r["formation_date_yac"])
            assert total == pytest.approx(chronology.age_of_earth, rel=1e-12)

    def test_acceleration_is_cumulative_not_instantaneous(self, solved):
        # They are different quantities and both are reported; a row where
        # they were equal would mean one of them is wrong.
        model, chronology, _ = solved
        _, rows = parse(to_csv(model, chronology, points=200, generated=STAMP))
        flood = [r for r in rows
                 if float(r["true_age_ybp"]) > chronology.flood_end_age]
        assert flood
        r = flood[0]
        assert float(r["acceleration_ratio"]) != float(r["lambda_at_formation"])

    def test_the_present_has_no_acceleration(self, solved):
        # 0/0. Blank, rather than a made-up limit.
        model, chronology, _ = solved
        _, rows = parse(to_csv(model, chronology, points=20, generated=STAMP))
        now = [r for r in rows if float(r["true_age_ybp"]) == 0.0][0]
        assert now["acceleration_ratio"] == ""

    def test_every_number_round_trips(self, solved):
        # `repr` is the shortest string that parses back to the same float.
        # Fixed decimals would quietly discard precision the model has.
        model, chronology, _ = solved
        text = to_csv(model, chronology, points=100, generated=STAMP)
        _, rows = parse(text)
        for r in rows:
            for col in COLUMNS:
                if r[col] == "":
                    continue
                assert repr(float(r[col])) == r[col]


# ---------------------------------------------------------------- provenance
class TestProvenance:
    def test_header_carries_everything_needed_to_rebuild_the_model(self, solved):
        # With free parameters most downloads describe a model that exists
        # nowhere else, so a file without its chronology is an unreproducible
        # number.
        model, chronology, constraints = solved
        header, _ = parse(to_csv(model, chronology, points=20,
                                 constraints=constraints, generated=STAMP))
        text = "\n".join(header)
        for field in ("age_of_earth", "flood_start_date", "flood_end_date",
                      "ice_age_end_date"):
            assert field in text
        for field in ("lambda_c", "k_c", "t_c", "lambda_F", "k_F", "t_F",
                      "t_F2", "k_PF", "lambda_bg"):
            assert f"{field}=" in text

    def test_the_parameter_line_round_trips_through_from_dict(self, solved):
        from card.models import GeneralModelParams

        model, chronology, _ = solved
        header, _ = parse(to_csv(model, chronology, points=20, generated=STAMP))
        line = [h for h in header if h.startswith("# parameters:")][0]
        pairs = dict(p.split("=") for p in line.split(":", 1)[1].split())
        rebuilt = GeneralModelParams.from_dict(
            {k: float(v) for k, v in pairs.items()})
        assert rebuilt == model.params

    def test_lambda_F2_is_reported_but_not_as_a_parameter(self, solved):
        # It is pinned by continuity at t_F2. Listing it among the parameters
        # would produce a header that does not round-trip through `from_dict`.
        model, chronology, _ = solved
        header, _ = parse(to_csv(model, chronology, points=20, generated=STAMP))
        params_line = [h for h in header if h.startswith("# parameters:")][0]
        assert "lambda_F2" not in params_line
        assert any(h.startswith("# lambda_F2:") for h in header)

    def test_constraints_are_reported_with_their_residuals(self, solved):
        model, chronology, constraints = solved
        header, _ = parse(to_csv(model, chronology, points=20,
                                 constraints=constraints, generated=STAMP))
        lines = [h for h in header if h.startswith("# constraint:")]
        assert len(lines) == len(constraints)
        assert all("residual" in ln for ln in lines)


# -------------------------------------------------------------- reproducible
class TestReproducible:
    def test_same_inputs_give_identical_bytes(self, solved):
        model, chronology, constraints = solved
        a = to_csv(model, chronology, points=100, constraints=constraints,
                   generated=STAMP)
        b = to_csv(model, chronology, points=100, constraints=constraints,
                   generated=STAMP)
        assert a == b

    def test_the_timestamp_is_the_only_moving_part(self, solved):
        # Which is why it is an argument. If anything else varied, the claim
        # that a browser download equals a CLI run could not be tested.
        model, chronology, _ = solved
        a = to_csv(model, chronology, points=50, generated=STAMP)
        b = to_csv(model, chronology, points=50,
                   generated=datetime(2030, 1, 1, tzinfo=timezone.utc))
        differing = [x for x, y in zip(a.splitlines(), b.splitlines()) if x != y]
        assert len(differing) == 1
        assert differing[0].startswith("# generated:")

    def test_a_different_chronology_changes_the_rows(self, solved):
        # Guards against the chronology being decorative in the header while
        # the numbers come from the default one.
        model, _, _ = solved
        other = Chronology(age_of_earth=7500.0, flood_start_date=2176.0,
                           flood_end_date=2177.0, ice_age_end_date=3300.0)
        a = to_csv(model, DEFAULT_CHRONOLOGY, points=50, generated=STAMP)
        b = to_csv(model, other, points=50, generated=STAMP)
        assert a != b


def test_ends_with_a_newline(solved):
    model, chronology, _ = solved
    assert to_csv(model, chronology, points=10, generated=STAMP).endswith("\n")
