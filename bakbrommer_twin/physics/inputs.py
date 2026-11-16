"""Plain data records that cross the boundary into the vehicle model each step."""

from __future__ import annotations


class RiderInputs:
    """What the rider does with hands and feet (mechanical inputs)."""

    __slots__ = ("brake_front", "brake_rear", "gear", "mode_request", "steer", "throttle")

    def __init__(self) -> None:
        self.throttle = 0.0  # twist grip, 0…1
        self.brake_front = 0.0  # front brake lever, 0…1
        self.brake_rear = 0.0  # rear brake lever/pedal, 0…1
        self.steer = 0.0  # handlebar angle, rad (+ = left)
        self.gear = 1  # requested gear (0 = neutral)
        self.mode_request = 0  # ride mode switch position (index into RIDE_MODES)


class DriveCommands:
    """What the controller asks of the actuators."""

    __slots__ = ("engine_throttle", "ignition", "starter", "torque_left", "torque_right")

    def __init__(self) -> None:
        self.torque_left = 0.0  # Nm at the left front wheel (+ drive, − regen)
        self.torque_right = 0.0  # Nm at the right front wheel
        self.engine_throttle = 0.0  # 0…1 (used only with throttle-by-wire)
        self.ignition = True  # petrol engine allowed to run
        self.starter = False  # crank the petrol engine


class Environment:
    """Road gradient, wind and air temperature at the vehicle's position."""

    __slots__ = ("air_temperature", "grade_cos", "grade_sin", "route_heading", "wind_x",
                 "wind_y")

    def __init__(self, air_temperature: float) -> None:
        self.grade_sin = 0.0  # sin of the road gradient angle (+ = uphill along the route)
        self.grade_cos = 1.0
        self.route_heading = 0.0  # direction of "uphill" in the world frame, rad
        self.wind_x = 0.0  # wind velocity in the world frame, m/s
        self.wind_y = 0.0
        self.air_temperature = air_temperature  # °C
