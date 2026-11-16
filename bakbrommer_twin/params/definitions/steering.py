"""Parameters: steering geometry."""

from __future__ import annotations

from bakbrommer_twin.params.registry import Registry
from bakbrommer_twin.params.types import Status

STEERING_TYPES: tuple[str, ...] = ("centre_pivot", "ackermann")


def register(reg: Registry) -> None:
    """Declare steering parameters."""
    reg.category("steering", "Steering")
    reg.choice("steering.type", "centre_pivot", STEERING_TYPES, "Steering type",
               "centre_pivot: the whole front axle with the box turns about one "
               "vertical pin. ackermann: each front wheel turns on its own knuckle.")
    reg.number("steering.ratio", 1.0, "-", 0.5, 5.0, "Steering ratio",
               "Handlebar angle divided by the steering angle at the wheels.",
               Status.ESTIMATED)
    reg.number("steering.max_angle", 35.0, "deg", 5.0, 70.0, "Maximum wheel steering angle",
               "Largest steering angle at the wheels (lock).", Status.ESTIMATED)
    reg.number("steering.pivot_offset", 0.0, "m", -0.5, 1.0, "Centre-pivot pin position",
               "Centre-pivot steering only: distance of the steering pin behind the "
               "front axle (0 = the pin sits on the axle line).")
    reg.number("steering.ackermann_percentage", 100.0, "%", 0.0, 150.0, "Ackermann percentage",
               "Ackermann steering only: 100 % = inner wheel steers exactly as much "
               "more as pure rolling needs, 0 % = both wheels parallel.")
