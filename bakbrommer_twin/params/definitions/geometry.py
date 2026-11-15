"""Parameters: vehicle geometry and mass distribution.

Positions use the *design frame*: origin on the ground under the middle of the
front axle, ``x`` = distance behind the front axle, ``y`` = to the left,
``height`` = above the ground. Measure with the vehicle standing level.
"""

from __future__ import annotations

from bakbrommer_twin.params.registry import Registry
from bakbrommer_twin.params.types import Status

EST = Status.ESTIMATED


def register(reg: Registry) -> None:
    """Declare geometry and mass parameters."""
    reg.category("geometry", "Geometry")
    reg.number("geometry.wheelbase", 1.60, "m", 0.8, 3.0, "Wheelbase",
               "Distance from the front axle to the rear axle.", EST)
    reg.number("geometry.front_track", 0.85, "m", 0.4, 1.6, "Front track width",
               "Distance between the centres of the two front tyres.", EST)

    reg.category("mass", "Mass and load")
    _component(reg, "chassis", "Chassis", 130.0, 0.85, 0.40,
               "Empty vehicle: frame, cargo box, wheels, motors, engine. "
               "Without battery, fuel, rider and cargo.")
    reg.number("mass.chassis.gyradius_roll", 0.30, "m", 0.05, 1.0, "Chassis roll gyradius",
               "Radius of gyration of the empty vehicle about its lengthwise axis. "
               "Roll inertia = mass × gyradius².")
    reg.number("mass.chassis.gyradius_pitch", 0.60, "m", 0.05, 1.5, "Chassis pitch gyradius",
               "Radius of gyration of the empty vehicle about its crosswise axis.")
    reg.number("mass.chassis.gyradius_yaw", 0.65, "m", 0.05, 1.5, "Chassis yaw gyradius",
               "Radius of gyration of the empty vehicle about its vertical axis.")
    _component(reg, "battery", "Battery", 14.0, 0.90, 0.35, "Traction battery pack.")
    _component(reg, "rider", "Rider", 80.0, 1.15, 0.95, "Rider including clothing and helmet.")
    reg.number("mass.rider.gyradius", 0.28, "m", 0.05, 0.6, "Rider gyradius",
               "Radius of gyration of the seated rider (same value used for all axes).")
    _component(reg, "cargo", "Cargo", 0.0, -0.05, 0.55,
               "Load in the cargo box. The height is the centre of the load, "
               "so a taller load needs a larger height.")
    reg.number("mass.cargo.length", 0.80, "m", 0.1, 2.0, "Cargo length",
               "Length of the load (used for its rotational inertia).")
    reg.number("mass.cargo.width", 0.60, "m", 0.1, 1.5, "Cargo width",
               "Width of the load (used for its rotational inertia).")
    reg.number("mass.cargo.stack_height", 0.40, "m", 0.05, 1.5, "Cargo stack height",
               "Height of the load from its bottom to its top (used for its inertia).")
    _component(reg, "fuel", "Fuel", 3.0, 1.20, 0.60, "Petrol in the tank (treated as fixed).")


def _component(reg: Registry, key: str, title: str, mass: float, x: float, height: float,
               what: str) -> None:
    """Declare mass and position of one mass component."""
    reg.number(f"mass.{key}.mass", mass, "kg", 0.0, 400.0, f"{title} mass", what, EST)
    reg.number(f"mass.{key}.x", x, "m", -1.0, 3.0, f"{title} position behind front axle",
               f"Centre of the {title.lower()} mass, measured backwards from the front axle "
               "(negative = ahead of the axle).", EST)
    reg.number(f"mass.{key}.y", 0.0, "m", -0.6, 0.6, f"{title} sideways offset",
               f"Centre of the {title.lower()} mass, to the left of the centre line "
               "(negative = to the right).")
    reg.number(f"mass.{key}.height", height, "m", 0.0, 2.0, f"{title} height",
               f"Height of the centre of the {title.lower()} mass above the ground.", EST)
