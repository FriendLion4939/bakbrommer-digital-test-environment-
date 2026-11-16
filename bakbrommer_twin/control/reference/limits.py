"""Protective limits: battery current, low voltage, motor temperature, rollover.

Each limiter returns a factor 0…1 that scales the torque request.
"""

from __future__ import annotations

from bakbrommer_twin.params.paramset import ParamSet


def _ramp(value: float, full: float, zero: float) -> float:
    """1 at ``full``, 0 at ``zero``, linear in between, clamped."""
    factor = (value - zero) / (full - zero)
    return 0.0 if factor < 0.0 else (1.0 if factor > 1.0 else factor)


class PowerLimiter:
    """Keeps battery current, battery voltage and motor temperature within limits.

    Battery current: a prediction (torque × wheel speed / efficiency / voltage)
    scales the request before it is sent; an integrating trim on the *measured*
    current corrects what the prediction gets wrong.
    """

    def __init__(self, params: ParamSet) -> None:
        self.discharge_limit = params.num("control.limits.battery_current")
        self.charge_limit = params.num("control.limits.charge_current")
        self.efficiency = params.num("control.limits.assumed_efficiency")
        self.gain = params.num("control.limits.current_gain")
        self.low_voltage_start = params.num("control.limits.low_voltage_start")
        self.low_voltage_end = params.num("control.limits.low_voltage_end")
        self.temp_start = params.num("control.limits.motor_temp_start")
        self.temp_end = params.num("control.limits.motor_temp_end")
        if self.low_voltage_start <= self.low_voltage_end:
            raise ValueError("control.limits.low_voltage_start must be above low_voltage_end")
        if self.temp_end <= self.temp_start:
            raise ValueError("control.limits.motor_temp_end must be above motor_temp_start")
        self.drive_trim = 1.0  # feedback factor on driving torque
        self.regen_trim = 1.0  # feedback factor on braking torque
        self.factor = 1.0  # last factor applied (for the charts)

    def reset(self) -> None:
        """Forget the feedback trims."""
        self.drive_trim = self.regen_trim = self.factor = 1.0

    def step(self, dt: float, driving: bool, power: float, share: float, voltage: float,
             current: float, motor_temp: float) -> float:
        """Return the torque factor for a torque request.

        ``driving`` says whether the request drives (True) or brakes (False);
        ``power`` is its mechanical power (W, + = driving). ``share`` is the
        ride mode's share of the discharge limit; ``voltage`` and ``current``
        are the measured battery values; ``motor_temp`` the hotter motor.
        """
        voltage = voltage if voltage > 1.0 else 1.0
        if driving:
            limit = self.discharge_limit * share
            predicted = power / (self.efficiency * voltage)
            factor = limit / predicted if predicted > limit else 1.0
            self.drive_trim += self.gain * (1.0 - current / limit) * dt
            self.drive_trim = min(1.0, max(0.0, self.drive_trim))
            self.regen_trim = min(1.0, self.regen_trim + self.gain * dt)
            factor *= self.drive_trim
            factor *= _ramp(voltage, self.low_voltage_start, self.low_voltage_end)
        else:
            limit = self.charge_limit
            predicted = -power * self.efficiency / voltage
            factor = limit / predicted if predicted > limit and limit > 0.0 else 1.0
            if limit <= 0.0:
                factor = 0.0
            else:
                self.regen_trim += self.gain * (1.0 + current / limit) * dt
                self.regen_trim = min(1.0, max(0.0, self.regen_trim))
            self.drive_trim = min(1.0, self.drive_trim + self.gain * dt)
            factor *= self.regen_trim
        factor *= _ramp(motor_temp, self.temp_start, self.temp_end)
        self.factor = factor
        return factor


class StabilityLimiter:
    """Rollover protection: less drive torque when cornering near the wheel-lift limit."""

    def __init__(self, params: ParamSet) -> None:
        self.enabled = params.flag("control.stability.enabled")
        self.accel_start = params.num("control.stability.accel_start")
        self.accel_end = params.num("control.stability.accel_end")
        self.min_factor = params.num("control.stability.min_torque_factor")
        self.roll_rate_limit = params.num("control.stability.roll_rate_limit")
        self.hold_time = params.num("control.stability.hold_time")
        if self.accel_end <= self.accel_start:
            raise ValueError("control.stability.accel_end must be above accel_start")
        self.factor = 1.0
        self._hold = 0.0  # s of full intervention left after a roll rate trigger

    def reset(self) -> None:
        """Forget any intervention."""
        self.factor = 1.0
        self._hold = 0.0

    def step(self, dt: float, lateral_accel: float, roll_rate: float) -> float:
        """Return the drive torque factor (``min_factor`` … 1)."""
        if not self.enabled:
            return 1.0
        if abs(roll_rate) > self.roll_rate_limit:
            self._hold = self.hold_time
        elif self._hold > 0.0:
            self._hold -= dt
        if self._hold > 0.0:
            self.factor = self.min_factor
        else:
            remaining = _ramp(abs(lateral_accel), self.accel_start, self.accel_end)
            self.factor = self.min_factor + (1.0 - self.min_factor) * remaining
        return self.factor
