"""Steering geometry: handlebar angle → position and angle of each front wheel.

Two geometries are supported:

``centre_pivot``
    The whole front axle (with the cargo box) turns about one vertical pin.
    Both wheels get the same steering angle δ and *move*: a wheel at
    (d, y_w) relative to the pin goes to (d·cos δ − y_w·sin δ,
    d·sin δ + y_w·cos δ). The moving contact points change the tipping line,
    so this matters for wheel lift. Simplification: the cargo mass is not
    moved with the axle (docs/PHYSICS.md, "Known simplifications").

``ackermann``
    Each wheel turns on its own knuckle; positions stay fixed. For a mean
    angle δ the ideal (pure rolling) angles are
        δ_left  = atan(L·tan δ / (L − (t/2)·tan δ))
        δ_right = atan(L·tan δ / (L + (t/2)·tan δ))
    (all wheel axes meet in one point on the rear axle line). The Ackermann
    percentage blends between parallel steering (0 %) and the ideal (100 %).

Extension point for tilting: a tilting geometry would be a third branch in
:meth:`Steering.apply` that also sets a camber angle per wheel; the tyre model
would then need a camber-thrust term.
"""

from __future__ import annotations

import math

from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics.wheels import FRONT_LEFT, FRONT_RIGHT, Wheel


class Steering:
    """Applies a handlebar angle to the two front wheels."""

    __slots__ = ("ackermann", "centre_pivot", "half_track", "handlebar", "max_angle",
                 "pivot_offset", "ratio", "wheel_angle", "wheelbase")

    def __init__(self, params: ParamSet) -> None:
        self.centre_pivot = params.choice("steering.type") == "centre_pivot"
        self.ratio = params.num("steering.ratio")
        self.max_angle = params.num("steering.max_angle")
        self.pivot_offset = params.num("steering.pivot_offset")
        self.ackermann = params.num("steering.ackermann_percentage")
        self.wheelbase = params.num("geometry.wheelbase")
        self.half_track = params.num("geometry.front_track") / 2.0
        self.handlebar = math.nan  # last applied handlebar angle, rad (nan = none yet)
        self.wheel_angle = 0.0  # mean steering angle at the wheels, rad

    def max_handlebar_angle(self) -> float:
        """Handlebar angle at full lock, rad."""
        return self.max_angle * self.ratio

    def apply(self, handlebar: float, wheels: list[Wheel]) -> None:
        """Set steering angle and position of the front wheels for ``handlebar`` (rad)."""
        if handlebar == self.handlebar:
            return  # nothing changed since the last step
        self.handlebar = handlebar
        angle = handlebar / self.ratio
        angle = max(-self.max_angle, min(self.max_angle, angle))
        self.wheel_angle = angle
        left, right = wheels[FRONT_LEFT], wheels[FRONT_RIGHT]
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        if self.centre_pivot:
            d = self.pivot_offset  # the axle is this far ahead of the pin
            for wheel, side in ((left, self.half_track), (right, -self.half_track)):
                pin_x = wheel.base_x - d
                pin_y = wheel.base_y - side
                wheel.x = pin_x + d * cos_a - side * sin_a
                wheel.y = pin_y + d * sin_a + side * cos_a
                wheel.steer = angle
                wheel.cos_steer = cos_a
                wheel.sin_steer = sin_a
        else:
            tan_a = sin_a / cos_a
            ideal_left = math.atan2(self.wheelbase * tan_a,
                                    self.wheelbase - self.half_track * tan_a)
            ideal_right = math.atan2(self.wheelbase * tan_a,
                                     self.wheelbase + self.half_track * tan_a)
            for wheel, ideal in ((left, ideal_left), (right, ideal_right)):
                wheel.steer = angle + self.ackermann * (ideal - angle)
                wheel.cos_steer = math.cos(wheel.steer)
                wheel.sin_steer = math.sin(wheel.steer)
