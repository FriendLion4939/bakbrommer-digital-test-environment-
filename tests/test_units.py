"""Unit conversion table."""

import math

import pytest

from bakbrommer_twin.params import units


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (36.0, "km/h", 10.0),
        (60.0, "rpm", 2.0 * math.pi),
        (180.0, "deg", math.pi),
        (1.0, "Ah", 3600.0),
        (50.0, "%", 0.5),
        (2.0, "kN/m", 2000.0),
        (1.0, "bar", 1e5),
        (25.0, "°C", 25.0),
    ],
)
def test_to_si(value: float, unit: str, expected: float) -> None:
    assert units.to_si(value, unit) == pytest.approx(expected)


def test_round_trip_every_unit() -> None:
    for unit in units.UNITS:
        assert units.from_si(units.to_si(1.234, unit), unit) == pytest.approx(1.234)


def test_unknown_unit_is_reported() -> None:
    with pytest.raises(units.UnknownUnitError, match="furlong"):
        units.to_si(1.0, "furlong")


def test_compatible_units() -> None:
    assert set(units.compatible_units("km/h")) == {"m/s", "km/h"}
