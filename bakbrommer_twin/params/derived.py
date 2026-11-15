"""Derived values: numbers calculated from the parameters, shown in the UI.

To add a derived value, append a :class:`DerivedValue` in one of the group
functions below (or add a new group function to ``_GROUPS``). The calculation
itself must live in a physics module so the simulator and the UI agree.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from bakbrommer_twin.params import units
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics import mass


@dataclass(frozen=True)
class DerivedValue:
    """One calculated value. ``value`` is in SI; ``unit`` is the friendly unit."""

    key: str
    label: str
    value: float
    unit: str
    description: str
    group: str

    @property
    def display(self) -> float:
        """The value converted to its friendly unit."""
        return units.from_si(self.value, self.unit)


def _mass_values(p: ParamSet) -> list[DerivedValue]:
    group = "Mass and balance"
    props = mass.mass_properties(p)
    front_left, front_right, rear = mass.static_wheel_loads(p)
    weight = props.mass * mass.GRAVITY
    return [
        DerivedValue("total_mass", "Total mass", props.mass, "kg",
                     "Chassis + battery + rider + cargo + fuel.", group),
        DerivedValue("cog_x", "Centre of gravity behind front axle", props.cog_x, "m",
                     "Position of the combined centre of gravity.", group),
        DerivedValue("cog_y", "Centre of gravity sideways offset", props.cog_y, "m",
                     "Positive = left of the centre line.", group),
        DerivedValue("cog_height", "Centre of gravity height", props.cog_height, "m",
                     "Height of the combined centre of gravity above the ground.", group),
        DerivedValue("front_weight_share", "Weight on front wheels",
                     (front_left + front_right) / weight, "%",
                     "Share of the weight carried by the two front wheels at rest.", group),
        DerivedValue("load_front_left", "Front-left wheel load", front_left, "N",
                     "Vertical load at rest on level ground.", group),
        DerivedValue("load_front_right", "Front-right wheel load", front_right, "N",
                     "Vertical load at rest on level ground.", group),
        DerivedValue("load_rear", "Rear wheel load", rear, "N",
                     "Vertical load at rest on level ground.", group),
        DerivedValue("inertia_roll", "Roll inertia", props.inertia_roll, "kg·m²",
                     "Rotational inertia about the lengthwise axis through the CoG.", group),
        DerivedValue("inertia_pitch", "Pitch inertia", props.inertia_pitch, "kg·m²",
                     "Rotational inertia about the crosswise axis through the CoG.", group),
        DerivedValue("inertia_yaw", "Yaw inertia", props.inertia_yaw, "kg·m²",
                     "Rotational inertia about the vertical axis through the CoG.", group),
    ]


def _stability_values(p: ParamSet) -> list[DerivedValue]:
    group = "Stability"
    return [
        DerivedValue("lift_accel_left_turn", "Wheel-lift cornering limit, left turn",
                     mass.lift_threshold_accel(p, turn_left=True), "g0",
                     "Steady sideways acceleration at which the inner (left) front wheel "
                     "lifts. Rigid-vehicle estimate; the simulation is more exact.", group),
        DerivedValue("lift_accel_right_turn", "Wheel-lift cornering limit, right turn",
                     mass.lift_threshold_accel(p, turn_left=False), "g0",
                     "Steady sideways acceleration at which the inner (right) front wheel "
                     "lifts.", group),
        DerivedValue("tip_over_angle", "Tip-over roll angle", mass.tip_over_angle(p), "deg",
                     "Roll angle at which the centre of gravity is above the line through "
                     "the outer front tyre and the rear tyre. Beyond it the vehicle falls.",
                     group),
    ]


_GROUPS: tuple[Callable[[ParamSet], list[DerivedValue]], ...] = (_mass_values, _stability_values)


def compute_derived(params: ParamSet) -> list[DerivedValue]:
    """Calculate every derived value for a parameter set."""
    values: list[DerivedValue] = []
    for group in _GROUPS:
        values.extend(group(params))
    return values


def derived_dict(params: ParamSet) -> dict[str, float]:
    """Derived values as ``key -> SI value`` (handy in tests and reports)."""
    return {v.key: v.value for v in compute_derived(params)}
