"""
Young-earth chronology configuration for CARD.

Two time conventions coexist throughout this package, and **the name of a
quantity tells you which one it uses**:

    DATE — years after Day 1 of Creation.  Forward time; "t" in the paper.
           Day 1 of Creation is date 0 and the present is the largest date.
    AGE  — years before present (YBP).  "tau" in the paper.
           The present is age 0 and Day 1 of Creation is the largest age.

The two run in opposite directions and are related by

    age  = age_of_earth - date
    date = age_of_earth - age

Model *parameters* (t_c, t_F, t_F2) and the decay rate lambda(t) are DATEs,
because lambda is naturally defined on the forward Creation timeline.  Rock
*ages* — everything passed to or returned by forward_age/inverse_age — are
AGEs, because that is how both secular and young-earth ages are quoted, and
it is the convention the paper's headline result is derived in.

Historically these were module-level constants with an `_AGE` suffix that
meant "years after Creation" on one line and "years before present" nine
lines later, which caused a real fitting error (the Ice Age constraint was
fit at 3500 YBP instead of 2556).  Hence both the naming rule above and this
class, which keeps the chronology in one editable, serializable place.
"""

import json
import warnings
from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class Chronology:
    """
    A young-earth chronology: when the Earth began and when events happened.

    Every field is user-specifiable — these are modeling assumptions, not
    physical constants.  Construct a variant with `dataclasses.replace`, or
    load one from a JSON config file with `Chronology.from_json_file`.

    Attributes:
        age_of_earth: Age of Day 1 of Creation, in years before present.
            Numerically this is also the present's DATE, since dates are
            measured from Day 1 — `present_date` exposes that reading.
        flood_start_date: DATE at which the Flood begins.
        flood_end_date: DATE at which the Flood ends.  One year after
            flood_start_date by default — the year-long Flood the model is
            written around.  Setting it equal to flood_start_date recovers the
            instantaneous-Flood limit, which is a degenerate case the model
            still accepts but no longer assumes.
        ice_age_end_date: DATE at which the Ice Age ends.
    """

    # Default values
    age_of_earth: float = 6056.0
    flood_start_date: float = 1656.0
    flood_end_date: float = 1657.0
    ice_age_end_date: float = 3500.0

    def __post_init__(self):
        if not self.age_of_earth > 0:
            raise ValueError(
                f"age_of_earth must be positive, got {self.age_of_earth!r}"
            )
        for name in ("flood_start_date", "flood_end_date", "ice_age_end_date"):
            date = getattr(self, name)
            if not 0.0 <= date <= self.age_of_earth:
                raise ValueError(
                    f"{name} ({date!r}) must be a DATE in "
                    f"[0, age_of_earth={self.age_of_earth}].  Dates count "
                    "years *after* Day 1 of Creation; if you meant years "
                    "before present, convert with age_to_date()."
                )
        if self.flood_end_date < self.flood_start_date:
            raise ValueError(
                f"flood_end_date ({self.flood_end_date}) precedes "
                f"flood_start_date ({self.flood_start_date})."
            )
        if self.ice_age_end_date < self.flood_end_date:
            raise ValueError(
                f"ice_age_end_date ({self.ice_age_end_date}) precedes "
                f"flood_end_date ({self.flood_end_date}); the Ice Age is "
                "understood to follow the Flood."
            )

    # ---------------------------------------------------------------- convert
    def date_to_age(self, date: float) -> float:
        """Convert a DATE (years after Creation) to an AGE (years before present)."""
        return self.age_of_earth - date

    def age_to_date(self, age: float) -> float:
        """Convert an AGE (years before present) to a DATE (years after Creation)."""
        return self.age_of_earth - age

    # ------------------------------------------------------------- derived
    @property
    def present_date(self) -> float:
        """DATE of the present — the same number as age_of_earth."""
        return self.age_of_earth

    @property
    def flood_start_age(self) -> float:
        """AGE (YBP) at which the Flood begins."""
        return self.date_to_age(self.flood_start_date)

    @property
    def flood_end_age(self) -> float:
        """AGE (YBP) at which the Flood ends."""
        return self.date_to_age(self.flood_end_date)

    @property
    def flood_duration(self) -> float:
        """
        Length of the Flood in true years — one, unless configured otherwise.

        This is what fixes the model's `t_F2`, which is no longer a free
        parameter: the Flood's length is a chronology assumption, so changing
        it here changes it everywhere rather than requiring a model parameter
        to be pinned by hand at each call site.
        """
        return self.flood_end_date - self.flood_start_date

    @property
    def ice_age_end_age(self) -> float:
        """AGE (YBP) at which the Ice Age ends."""
        return self.date_to_age(self.ice_age_end_date)

    # --------------------------------------------------------- serialization
    def to_dict(self) -> Dict[str, float]:
        """Plain-dict form, suitable for JSON or a GUI form."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Chronology":
        """Build from a plain dict, ignoring unknown keys with a warning."""
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            warnings.warn(
                f"Ignoring unrecognized chronology keys: {sorted(unknown)}. "
                f"Known keys are {sorted(known)}.",
                stacklevel=2,
            )
        return cls(**{k: float(v) for k, v in data.items() if k in known})

    def to_json_file(self, path: str) -> None:
        """Write this chronology to a JSON config file."""
        with open(path, "w") as handle:
            json.dump(self.to_dict(), handle, indent=2)
            handle.write("\n")

    @classmethod
    def from_json_file(cls, path: str) -> "Chronology":
        """Load a chronology from a JSON config file."""
        with open(path) as handle:
            return cls.from_dict(json.load(handle))


# The chronology used when a caller does not supply one: Earth 6056 years old,
# the Flood running from 1656 to 1657 years after Creation, Ice Age ending 3500
# years after Creation.
DEFAULT_CHRONOLOGY = Chronology()


# ---------------------------------------------------------------------------
# Module-level conversions against the default chronology.
#
# `Chronology.date_to_age` / `age_to_date` are the same operations bound to a
# specific chronology; prefer those when a caller supplies one.  These spelled
# out names are kept because they read unambiguously at a call site.
# ---------------------------------------------------------------------------

def years_before_present_to_years_after_creation(
    years_ago: float, age_of_earth: float = None
) -> float:
    """
    Convert an AGE (years before present) to a DATE (years after Creation).

    Args:
        years_ago: AGE to convert.
        age_of_earth: Age of the Earth to measure against; defaults to the
            default chronology's value.

    Returns:
        The corresponding DATE.
    """
    if age_of_earth is None:
        age_of_earth = DEFAULT_CHRONOLOGY.age_of_earth
    return age_of_earth - years_ago


def years_after_creation_to_years_before_present(
    years_after: float, age_of_earth: float = None
) -> float:
    """
    Convert a DATE (years after Creation) to an AGE (years before present).

    Args:
        years_after: DATE to convert.
        age_of_earth: Age of the Earth to measure against; defaults to the
            default chronology's value.

    Returns:
        The corresponding AGE.
    """
    if age_of_earth is None:
        age_of_earth = DEFAULT_CHRONOLOGY.age_of_earth
    return age_of_earth - years_after
