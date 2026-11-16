"""Parameters: hydraulic brakes."""

from __future__ import annotations

from bakbrommer_twin.params.registry import Registry
from bakbrommer_twin.params.types import Status

EST = Status.ESTIMATED


def register(reg: Registry) -> None:
    """Declare brake parameters."""
    reg.category("brakes", "Brakes")
    for axle, pressure, area, radius in (("front", 60.0, 9.8, 90.0), ("rear", 50.0, 9.8, 85.0)):
        title = axle.capitalize()
        reg.number(f"brakes.{axle}_max_pressure", pressure, "bar", 5.0, 200.0,
                   f"{title} pressure at full lever",
                   f"Hydraulic pressure in the {axle} circuit with the lever fully pulled.",
                   EST)
        reg.number(f"brakes.{axle}_piston_area", area, "cm²", 1.0, 60.0,
                   f"{title} caliper piston area",
                   "Total piston area on one side of one caliper.", EST)
        reg.number(f"brakes.{axle}_pad_friction", 0.40, "-", 0.1, 0.8,
                   f"{title} pad friction", "Friction coefficient between pad and disc.", EST)
        reg.number(f"brakes.{axle}_disc_radius", radius, "mm", 30.0, 250.0,
                   f"{title} effective disc radius",
                   "Distance from the wheel axis to the middle of the brake pad.", EST)
    reg.number("brakes.response_time", 50.0, "ms", 1.0, 500.0, "Pressure build-up time",
               "Time constant with which the pressure follows the lever.", EST)
    reg.flag("brakes.linked", False, "Linked brakes",
             "On: either lever pressurises both circuits. Off: one lever works the "
             "two front brakes, the other the rear brake.")
    reg.number("brakes.linked_rear_share", 60.0, "%", 0.0, 100.0, "Linked rear pressure share",
               "Linked brakes only: rear pressure as a share of what the lever asks for.")
