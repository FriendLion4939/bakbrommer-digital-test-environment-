"""The "direct" controller: no hybrid logic at all.

Throttle maps linearly to the same torque on both motors, front brake
pressure maps to regen torque, the petrol engine is always allowed to run and
(with throttle-by-wire) gets the rider's throttle. It exists to test the
physics without the brain getting in the way, and as the simplest example of
the controller interface.
"""

from __future__ import annotations

from bakbrommer_twin.control.interface import ControllerInputs, ControllerOutputs
from bakbrommer_twin.params.paramset import ParamSet


class DirectController:
    """Throttle straight to both motors."""

    def __init__(self, params: ParamSet) -> None:
        self.max_torque = params.num("control.direct.max_torque")
        self.regen_torque = params.num("control.direct.regen_torque")
        self.full_brake_pressure = params.num("brakes.front_max_pressure")

    def reset(self) -> None:
        """Nothing to reset: this controller has no memory."""

    def step(self, inputs: ControllerInputs, outputs: ControllerOutputs) -> None:
        """Compute the commands for this control period."""
        throttle = min(1.0, max(0.0, inputs.throttle))
        brake = min(1.0, max(0.0, inputs.brake_front_pressure / self.full_brake_pressure))
        torque = throttle * self.max_torque - brake * self.regen_torque
        outputs.torque_left = torque
        outputs.torque_right = torque
        outputs.engine_throttle = throttle
        outputs.engine_ignition = 1.0
        outputs.engine_starter = 0.0
        outputs.active_mode = inputs.mode_request
        outputs.diag_speed_estimate = inputs.vehicle_speed
        outputs.diag_regen_torque = brake * self.regen_torque
