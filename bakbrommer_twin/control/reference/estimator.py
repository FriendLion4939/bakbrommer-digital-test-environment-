"""Vehicle speed estimate from wheel speeds and the accelerometer.

Wheel speed sensors lie when a wheel spins or locks. The estimate therefore
takes the *slowest* wheel while driving (a spinning wheel is too fast) and
the *fastest* wheel while braking (a locking wheel is too slow), and it may
not change faster than the accelerometer allows (± a margin).

Front wheel speeds are first referred to the vehicle centre line: in a turn
with yaw rate r the left wheel runs r·t/2 slower and the right wheel r·t/2
faster than the centre (t = track width).
"""

from __future__ import annotations

from bakbrommer_twin.control.interface import ControllerInputs
from bakbrommer_twin.params.paramset import ParamSet


class SpeedEstimator:
    """Estimates the forward speed of the vehicle, m/s."""

    def __init__(self, params: ParamSet) -> None:
        self.front_radius = params.num("wheels.front_radius")
        self.rear_radius = params.num("wheels.rear_radius")
        self.half_track = params.num("geometry.front_track") / 2.0
        self.margin = params.num("control.estimator_accel_margin")
        self.use_sensor = params.flag("control.estimator_use_speed_sensor")
        self.speed = 0.0  # the estimate, m/s
        self.left = 0.0  # front-left wheel speed referred to the centre line, m/s
        self.right = 0.0  # front-right wheel speed referred to the centre line, m/s
        self._started = False

    def reset(self) -> None:
        """Forget the estimate (the next step starts from the wheel speeds)."""
        self.speed = 0.0
        self._started = False

    def step(self, inputs: ControllerInputs, driving: bool) -> float:
        """Update and return the estimate. ``driving`` = throttle open, brakes released."""
        yaw_part = inputs.gyro_z * self.half_track
        left = inputs.wheel_speed_fl * self.front_radius + yaw_part
        right = inputs.wheel_speed_fr * self.front_radius - yaw_part
        rear = inputs.wheel_speed_r * self.rear_radius
        self.left, self.right = left, right
        if driving:
            candidate = min(left, right, rear)
            if self.use_sensor and inputs.vehicle_speed < candidate:
                candidate = inputs.vehicle_speed
        else:
            candidate = max(left, right, rear)
            if self.use_sensor and inputs.vehicle_speed > candidate:
                candidate = inputs.vehicle_speed
        if not self._started:
            self._started = True
            self.speed = max(0.0, candidate)
            return self.speed
        # Plausibility window from the accelerometer: v_prev + (a_x ± margin)·dt.
        predicted = self.speed + inputs.accel_x * inputs.dt
        window = self.margin * inputs.dt
        speed = min(max(candidate, predicted - window), predicted + window)
        self.speed = max(0.0, speed)
        return self.speed
