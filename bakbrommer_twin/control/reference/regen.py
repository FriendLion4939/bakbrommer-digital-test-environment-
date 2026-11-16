"""Regenerative braking request.

Electric braking torque per motor =
    (coast regen of the ride mode, when the throttle is closed
     + brake regen of the ride mode × brake fraction)
    brake fraction = (front pressure − threshold) / (full pressure − threshold)
    × speed fade (none at walking pace) × voltage fade (none when the battery is full)
"""

from __future__ import annotations

from bakbrommer_twin.control.reference.modes import ModeSettings
from bakbrommer_twin.params.paramset import ParamSet


class Regen:
    """Computes the regen torque request (Nm per motor, ≥ 0)."""

    def __init__(self, params: ParamSet) -> None:
        self.throttle_deadband = params.num("control.regen.throttle_deadband")
        self.brake_threshold = params.num("control.regen.brake_threshold")
        self.full_pressure = params.num("control.regen.full_pressure")
        if self.full_pressure <= self.brake_threshold:
            raise ValueError("control.regen.full_pressure must be above brake_threshold")
        self.fade_start = params.num("control.regen.fade_start_speed")
        self.fade_end = params.num("control.regen.fade_end_speed")
        self.voltage_start = params.num("control.regen.voltage_start")
        self.voltage_end = params.num("control.regen.voltage_end")
        if self.fade_end <= self.fade_start:
            raise ValueError("control.regen.fade_end_speed must be above fade_start_speed")
        if self.voltage_end <= self.voltage_start:
            raise ValueError("control.regen.voltage_end must be above voltage_start")

    def step(self, mode: ModeSettings, throttle: float, brake_pressure: float, speed: float,
             voltage: float) -> float:
        """Return the regen torque request per motor, Nm (0 = none)."""
        if throttle > self.throttle_deadband:
            return 0.0
        brake = (brake_pressure - self.brake_threshold) / (
            self.full_pressure - self.brake_threshold)
        brake = 0.0 if brake < 0.0 else (1.0 if brake > 1.0 else brake)
        torque = mode.coast_regen_torque + brake * mode.brake_regen_torque
        speed_fade = (speed - self.fade_start) / (self.fade_end - self.fade_start)
        if speed_fade <= 0.0:
            return 0.0
        if speed_fade < 1.0:
            torque *= speed_fade
        voltage_fade = (self.voltage_end - voltage) / (self.voltage_end - self.voltage_start)
        if voltage_fade <= 0.0:
            return 0.0
        if voltage_fade < 1.0:
            torque *= voltage_fade
        return torque
