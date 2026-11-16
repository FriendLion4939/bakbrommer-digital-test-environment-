"""Parameters: aerodynamics and environment (air, wind)."""

from __future__ import annotations

from bakbrommer_twin.params.definitions.wheels import SURFACE_NAMES
from bakbrommer_twin.params.registry import Registry
from bakbrommer_twin.params.types import Status

EST = Status.ESTIMATED

# Cargo box shape -> default drag coefficient. Add a shape by adding a line.
_BOX_SHAPES: dict[str, float] = {
    "open_box": 1.05,
    "closed_box": 0.90,
    "streamlined": 0.70,
    "no_box": 0.80,
}
BOX_SHAPES: tuple[str, ...] = tuple(_BOX_SHAPES)


def register(reg: Registry) -> None:
    """Declare aerodynamic and environment parameters."""
    reg.category("aero", "Aerodynamics")
    reg.number("aero.frontal_area", 1.0, "m²", 0.3, 3.0, "Frontal area",
               "Area of vehicle plus rider seen from the front.", EST)
    reg.choice("aero.cargo_box_shape", "open_box", BOX_SHAPES, "Cargo box shape",
               "Selects which drag coefficient below is used.")
    for shape, cd in _BOX_SHAPES.items():
        reg.number(f"aero.cd_{shape}", cd, "-", 0.2, 2.0,
                   f"Drag coefficient: {shape.replace('_', ' ')}",
                   "Drag coefficient (Cd) used when this cargo box shape is selected.", EST)
    reg.number("aero.side_area", 1.2, "m²", 0.2, 4.0, "Side area",
               "Area of vehicle plus rider seen from the side (cross-wind force).", EST)
    reg.number("aero.cd_side", 1.1, "-", 0.3, 2.0, "Side force coefficient",
               "Force coefficient for air flowing across the vehicle.", EST)
    reg.number("aero.pressure_centre_height", 0.70, "m", 0.1, 1.8, "Height of air force",
               "Height above the ground at which the air force acts.", EST)
    reg.number("aero.pressure_centre_x", 0.70, "m", -0.5, 2.5, "Position of side air force",
               "Distance behind the front axle at which the cross-wind force acts.", EST)

    reg.category("environment", "Environment")
    reg.choice("environment.default_surface", SURFACE_NAMES[0], SURFACE_NAMES,
               "Default road surface",
               "Surface used wherever a scenario does not name one. Set it to "
               "wet_asphalt in a wet-weather profile.")
    reg.number("environment.air_density", 1.225, "kg/m³", 0.9, 1.5, "Air density",
               "Density of the air (1.225 at sea level and 15 °C).")
    reg.number("environment.air_temperature", 20.0, "°C", -20.0, 45.0, "Air temperature",
               "Outside temperature; starting temperature of motors and battery.")
    reg.number("environment.wind_speed", 0.0, "km/h", 0.0, 100.0, "Wind speed",
               "Steady wind speed.")
    reg.number("environment.wind_direction", 0.0, "deg", -180.0, 360.0, "Wind direction",
               "Where the wind comes from, measured from the starting direction of the "
               "route: 0 = headwind at the start, 90 = from the left, 180 = tailwind.")
