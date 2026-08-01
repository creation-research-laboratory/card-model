"""
Tests for the Chronology config and the AGE/DATE naming rule.

The naming rule is that a quantity named *_DATE counts years AFTER Day 1 of
Creation, and a quantity named *_AGE counts years BEFORE PRESENT.  Getting
these backwards previously caused a real fitting error (the Ice Age
constraint was fit at 3500 YBP when it should have been 2556), so the
relationships between the constants are pinned here rather than left to
convention alone.
"""

import dataclasses
import json

import pytest

from card import DEFAULT_CHRONOLOGY, Chronology
from card import (
    AGE_OF_EARTH,
    FLOOD_AGE,
    FLOOD_END_DATE,
    FLOOD_START_AGE,
    FLOOD_START_DATE,
    ICE_AGE_END_AGE,
    ICE_AGE_END_DATE,
    PRESENT_DATE,
)


# ----------------------------------------------------------------------------
# The naming rule: a DATE and its matching AGE must sum to the age of the Earth
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("date, age", [
    (FLOOD_START_DATE, FLOOD_START_AGE),
    (FLOOD_START_DATE, FLOOD_AGE),
    (ICE_AGE_END_DATE, ICE_AGE_END_AGE),
])
def test_date_and_age_are_complementary(date, age):
    assert date + age == AGE_OF_EARTH


def test_ice_age_constants_have_the_expected_orientation():
    """Guards the specific mix-up that caused the stale MCMC fit: the DATE is
    the larger number (3500 years after Creation), the AGE the smaller one
    (2556 years before present)."""
    assert ICE_AGE_END_DATE == 3500
    assert ICE_AGE_END_AGE == 2556
    assert ICE_AGE_END_DATE > ICE_AGE_END_AGE


def test_flood_constants_have_the_expected_orientation():
    assert FLOOD_START_DATE == 1656
    assert FLOOD_AGE == 4400
    assert FLOOD_END_DATE == FLOOD_START_DATE  # instantaneous Flood by default


def test_present_date_equals_age_of_earth():
    """Dates are measured from Day 1, so the present's DATE is numerically the
    Earth's AGE.  This coincidence is why the two conventions were confusable."""
    assert PRESENT_DATE == AGE_OF_EARTH


# ----------------------------------------------------------------------------
# Conversions
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("date", [0, 1, 1656, 3500, 6056])
def test_date_age_round_trip(date):
    chron = DEFAULT_CHRONOLOGY
    assert chron.age_to_date(chron.date_to_age(date)) == pytest.approx(date)


def test_conversions_run_in_opposite_directions():
    chron = DEFAULT_CHRONOLOGY
    assert chron.date_to_age(0) == chron.age_of_earth      # Creation
    assert chron.date_to_age(chron.age_of_earth) == 0      # present


# ----------------------------------------------------------------------------
# User-specifiable chronologies
# ----------------------------------------------------------------------------

def test_custom_chronology_redefines_derived_ages():
    """The paper's alternative chronology: Earth 6600 years old, Flood at
    5000 YBP."""
    chron = Chronology(age_of_earth=6600, flood_start_date=1600,
                       flood_end_date=1600, ice_age_end_date=3000)
    assert chron.flood_start_age == 5000
    assert chron.ice_age_end_age == 3600


def test_chronology_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_CHRONOLOGY.age_of_earth = 1234


def test_replace_produces_a_variant():
    variant = dataclasses.replace(DEFAULT_CHRONOLOGY, age_of_earth=7000)
    assert variant.flood_start_age == 7000 - DEFAULT_CHRONOLOGY.flood_start_date
    assert DEFAULT_CHRONOLOGY.age_of_earth == 6056  # original untouched


@pytest.mark.parametrize("kwargs", [
    {"age_of_earth": 0},
    {"age_of_earth": -100},
    {"flood_start_date": -1},
    {"flood_start_date": 99999},        # date beyond the present
    {"flood_start_date": 2000, "flood_end_date": 1000},   # ends before it starts
    {"ice_age_end_date": 1000},         # Ice Age ends before the Flood
])
def test_invalid_chronologies_are_rejected(kwargs):
    with pytest.raises(ValueError):
        Chronology(**kwargs)


def test_passing_an_age_where_a_date_belongs_is_caught():
    """A Flood AGE (4400 YBP) used as a DATE is still inside [0, age_of_earth],
    so it cannot be rejected outright — but it does place the Flood after the
    Ice Age, which is."""
    with pytest.raises(ValueError):
        Chronology(flood_start_date=4400, flood_end_date=4400)


# ----------------------------------------------------------------------------
# Config-file serialization
# ----------------------------------------------------------------------------

def test_dict_round_trip():
    assert Chronology.from_dict(DEFAULT_CHRONOLOGY.to_dict()) == DEFAULT_CHRONOLOGY


def test_json_file_round_trip(tmp_path):
    path = tmp_path / "chronology.json"
    chron = Chronology(age_of_earth=6600, flood_start_date=1600,
                       flood_end_date=1601, ice_age_end_date=3000)
    chron.to_json_file(str(path))
    assert Chronology.from_json_file(str(path)) == chron
    # and it is human-editable JSON, not a pickle
    assert json.loads(path.read_text())["age_of_earth"] == 6600


def test_unknown_config_keys_warn_rather_than_crash():
    with pytest.warns(UserWarning, match="unrecognized chronology keys"):
        chron = Chronology.from_dict({"age_of_earth": 6056, "typo_field": 1})
    assert chron.age_of_earth == 6056
