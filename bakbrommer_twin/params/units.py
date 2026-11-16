"""Unit conversion table.

All code works in SI units. Friendly units (km/h, rpm, deg, Ah, ...) exist only
in parameter definitions, YAML files, the UI and log import/export. This file
is the single place that knows how to convert between the two.

Each friendly unit maps to ``(si_unit, factor, offset)`` with
``si_value = friendly_value * factor + offset``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

# friendly unit -> (SI unit, factor, offset)
UNITS: dict[str, tuple[str, float, float]] = {
    # dimensionless
    "": ("", 1.0, 0.0),
    "-": ("-", 1.0, 0.0),
    "%": ("-", 0.01, 0.0),
    # length
    "m": ("m", 1.0, 0.0),
    "mm": ("m", 1e-3, 0.0),
    "cm": ("m", 1e-2, 0.0),
    "km": ("m", 1e3, 0.0),
    # mass
    "kg": ("kg", 1.0, 0.0),
    # time and rate
    "s": ("s", 1.0, 0.0),
    "ms": ("s", 1e-3, 0.0),
    "min": ("s", 60.0, 0.0),
    "h": ("s", 3600.0, 0.0),
    "Hz": ("Hz", 1.0, 0.0),
    "1/s": ("1/s", 1.0, 0.0),
    # angle
    "rad": ("rad", 1.0, 0.0),
    "deg": ("rad", math.pi / 180.0, 0.0),
    "1/rad": ("1/rad", 1.0, 0.0),
    "1/m": ("1/m", 1.0, 0.0),
    # speed
    "m/s": ("m/s", 1.0, 0.0),
    "km/h": ("m/s", 1.0 / 3.6, 0.0),
    # angular speed
    "rad/s": ("rad/s", 1.0, 0.0),
    "rpm": ("rad/s", 2.0 * math.pi / 60.0, 0.0),
    "deg/s": ("rad/s", math.pi / 180.0, 0.0),
    # acceleration
    "m/s²": ("m/s²", 1.0, 0.0),
    "g": ("m/s²", 9.80665, 0.0),  # acceleration in multiples of gravity
    "rad/s²": ("rad/s²", 1.0, 0.0),
    # force, torque, stiffness, damping
    "N": ("N", 1.0, 0.0),
    "kN": ("N", 1e3, 0.0),
    "Nm": ("Nm", 1.0, 0.0),
    "N/m": ("N/m", 1.0, 0.0),
    "kN/m": ("N/m", 1e3, 0.0),
    "Ns/m": ("Ns/m", 1.0, 0.0),
    "Nm/A": ("Nm/A", 1.0, 0.0),
    "Nm/(rad/s)": ("Nm/(rad/s)", 1.0, 0.0),
    "Nm/rad": ("Nm/rad", 1.0, 0.0),
    "Nm/s": ("Nm/s", 1.0, 0.0),
    "Nm·s/rad": ("Nm·s/rad", 1.0, 0.0),
    "Nm/rpm": ("Nm·s/rad", 60.0 / (2.0 * math.pi), 0.0),
    # power and energy
    "W": ("W", 1.0, 0.0),
    "kW": ("W", 1e3, 0.0),
    "J": ("J", 1.0, 0.0),
    "kJ": ("J", 1e3, 0.0),
    "Wh": ("J", 3600.0, 0.0),
    "kWh": ("J", 3.6e6, 0.0),
    "MJ/kg": ("J/kg", 1e6, 0.0),
    # electrical
    "V": ("V", 1.0, 0.0),
    "A": ("A", 1.0, 0.0),
    "Ah": ("A·s", 3600.0, 0.0),
    "Ω": ("Ω", 1.0, 0.0),
    "mΩ": ("Ω", 1e-3, 0.0),
    "F": ("F", 1.0, 0.0),
    "A/s": ("A/s", 1.0, 0.0),
    # thermal (temperatures stay in °C everywhere: only differences matter)
    "°C": ("°C", 1.0, 0.0),
    "K": ("K", 1.0, 0.0),
    "J/K": ("J/K", 1.0, 0.0),
    "K/W": ("K/W", 1.0, 0.0),
    "W/K": ("W/K", 1.0, 0.0),
    "1/K": ("1/K", 1.0, 0.0),
    # area, volume, density, inertia
    "m²": ("m²", 1.0, 0.0),
    "cm²": ("m²", 1e-4, 0.0),
    "mm²": ("m²", 1e-6, 0.0),
    "L": ("m³", 1e-3, 0.0),
    "kg/m³": ("kg/m³", 1.0, 0.0),
    "kg/L": ("kg/m³", 1e3, 0.0),
    "kg·m²": ("kg·m²", 1.0, 0.0),
    # pressure
    "Pa": ("Pa", 1.0, 0.0),
    "kPa": ("Pa", 1e3, 0.0),
    "bar": ("Pa", 1e5, 0.0),
    # consumption
    "L/100km": ("m³/m", 1e-3 / 1e5, 0.0),
    "L/h": ("m³/s", 1e-3 / 3600.0, 0.0),
    "Wh/km": ("J/m", 3.6, 0.0),
    "g/kWh": ("kg/J", 1e-3 / 3.6e6, 0.0),
    "W/kg": ("W/kg", 1.0, 0.0),
    "s²/m²": ("s²/m²", 1.0, 0.0),
    "s/m": ("s/m", 1.0, 0.0),
    "s/rad": ("s/rad", 1.0, 0.0),
}


class UnknownUnitError(KeyError):
    """Raised when a unit string is not in the UNITS table."""


def _lookup(unit: str) -> tuple[str, float, float]:
    try:
        return UNITS[unit]
    except KeyError as exc:
        raise UnknownUnitError(
            f"Unknown unit '{unit}'. Add it to bakbrommer_twin/params/units.py."
        ) from exc


def si_unit(unit: str) -> str:
    """Return the SI unit that a friendly unit converts to."""
    return _lookup(unit)[0]


def to_si(value: float, unit: str) -> float:
    """Convert one number from a friendly unit to SI."""
    _, factor, offset = _lookup(unit)
    return value * factor + offset


def from_si(value: float, unit: str) -> float:
    """Convert one number from SI to a friendly unit."""
    _, factor, offset = _lookup(unit)
    return (value - offset) / factor


def list_to_si(values: Sequence[float], unit: str) -> list[float]:
    """Convert a list of numbers from a friendly unit to SI."""
    return [to_si(float(v), unit) for v in values]


def list_from_si(values: Sequence[float], unit: str) -> list[float]:
    """Convert a list of numbers from SI to a friendly unit."""
    return [from_si(float(v), unit) for v in values]


def compatible_units(unit: str) -> list[str]:
    """All friendly units that share the same SI unit (for unit pickers in the UI)."""
    target = si_unit(unit)
    return [name for name, (si, _, _) in UNITS.items() if si == target and name != ""]
