"""Slip limiter: the core of traction control and of the regen anti-lock.

Given how much a wheel slips beyond the allowed value, it returns the share
of that wheel's torque to remove (0 = none, 1 = all):

    cut = clamp(k_p·excess + integral, 0, 1)
    integral grows with k_i·excess while slipping, shrinks at the recovery rate
    once the wheel grips again.

The proportional part reacts at once; the integral part finds the torque the
surface can actually carry and holds it.
"""

from __future__ import annotations

from bakbrommer_twin.params.paramset import ParamSet


class SlipLimiter:
    """PI limiter on wheel slip for one wheel."""

    def __init__(self, params: ParamSet, slip_target: float) -> None:
        self.slip_target = slip_target
        self.min_speed = params.num("control.traction.min_speed")
        self.proportional_gain = params.num("control.traction.proportional_gain")
        self.integral_gain = params.num("control.traction.integral_gain")
        self.recovery_rate = params.num("control.traction.recovery_rate")
        self.cut = 0.0  # share of torque removed right now, 0…1
        self._integral = 0.0

    def reset(self) -> None:
        """Forget any intervention."""
        self.cut = self._integral = 0.0

    def step(self, dt: float, wheel_speed: float, vehicle_speed: float, sign: float) -> float:
        """Update the cut. ``sign`` = +1 watches for spin (drive), −1 for lock (braking).

        Speeds are in m/s at the centre line. Returns the torque share to remove.
        """
        reference = vehicle_speed if vehicle_speed > self.min_speed else self.min_speed
        slip = sign * (wheel_speed - vehicle_speed) / reference
        excess = slip - self.slip_target
        if excess > 0.0:
            self._integral += self.integral_gain * excess * dt
            if self._integral > 1.0:
                self._integral = 1.0
            cut = self.proportional_gain * excess + self._integral
            self.cut = 1.0 if cut > 1.0 else cut
        else:
            self._integral -= self.recovery_rate * dt
            if self._integral < 0.0:
                self._integral = 0.0
            self.cut = self._integral
        return self.cut
