"""Hydraulic disc brakes.

Lever position → line pressure (first-order lag) → brake torque per wheel:

    T = 2·μ_pad·A_piston·p·r_eff

(the caliper clamps the disc from both sides, hence the factor 2; standard
disc brake relation, e.g. Limpert, "Brake Design and Safety"). The torque is
a *capacity*: the wheel model applies it as friction that can hold a wheel
still. One front circuit feeds both front calipers, one rear circuit the rear.
"""

from __future__ import annotations

from bakbrommer_twin.params.paramset import ParamSet


class Brakes:
    """Both brake circuits. Call :meth:`update` each step."""

    __slots__ = ("front_gain", "front_max_pressure", "front_pressure", "front_torque",
                 "linked", "linked_rear_share", "rear_gain", "rear_max_pressure",
                 "rear_pressure", "rear_torque", "response_time")

    def __init__(self, params: ParamSet) -> None:
        self.front_max_pressure = params.num("brakes.front_max_pressure")
        self.rear_max_pressure = params.num("brakes.rear_max_pressure")
        # torque per pascal: 2·μ·A·r, m³
        self.front_gain = (2.0 * params.num("brakes.front_pad_friction")
                           * params.num("brakes.front_piston_area")
                           * params.num("brakes.front_disc_radius"))
        self.rear_gain = (2.0 * params.num("brakes.rear_pad_friction")
                          * params.num("brakes.rear_piston_area")
                          * params.num("brakes.rear_disc_radius"))
        self.response_time = params.num("brakes.response_time")
        self.linked = params.flag("brakes.linked")
        self.linked_rear_share = params.num("brakes.linked_rear_share")
        self.front_pressure = 0.0  # Pa
        self.rear_pressure = 0.0  # Pa
        self.front_torque = 0.0  # Nm capacity at each front wheel
        self.rear_torque = 0.0  # Nm capacity at the rear wheel

    def update(self, dt: float, front_lever: float, rear_lever: float) -> None:
        """Advance the pressures. Lever positions are 0 (released) … 1 (fully pulled)."""
        if self.linked:
            lever = max(front_lever, rear_lever)
            front_target = lever * self.front_max_pressure
            rear_target = lever * self.linked_rear_share * self.rear_max_pressure
        else:
            front_target = front_lever * self.front_max_pressure
            rear_target = rear_lever * self.rear_max_pressure
        blend = min(1.0, dt / self.response_time)
        self.front_pressure += (front_target - self.front_pressure) * blend
        self.rear_pressure += (rear_target - self.rear_pressure) * blend
        self.front_torque = self.front_gain * self.front_pressure
        self.rear_torque = self.rear_gain * self.rear_pressure

    def max_front_torque(self) -> float:
        """Brake torque at one front wheel with the lever fully pulled, Nm."""
        return self.front_gain * self.front_max_pressure

    def max_rear_torque(self) -> float:
        """Brake torque at the rear wheel with the lever fully pulled, Nm."""
        share = self.linked_rear_share if self.linked else 1.0
        return self.rear_gain * self.rear_max_pressure * share
